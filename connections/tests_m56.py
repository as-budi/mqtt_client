"""Tes tahap M5/M6: sandbox IoT Platform, CA sendiri untuk mqtts://, dan elemen halaman koneksi."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import platform
from accounts.models import User

from .models import ConnectionProfile, RelayTicket
from .tests import form_data
from .tests_session import BROKER, SECRET, sign_in

SANDBOX = {"available": True, "enabled": True, "broker": BROKER,
           "manage_url": "https://iot.example.org/accounts/profile/",
           "username": "sbx-5", "password": "pw-sandbox", "topic_root": "sandbox/budi",
           "shared_root": "sandbox/public", "password_changed_at": None}


def make_certificate():
    """Sertifikat self-signed (PEM) dari openssl, atau None bila openssl tidak ada."""
    if not shutil.which("openssl"):
        return None
    with tempfile.TemporaryDirectory() as folder:
        cert = Path(folder) / "cert.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=lab",
                        "-keyout", str(Path(folder) / "key.pem"), "-out", str(cert)], check=True, capture_output=True)
        return cert.read_text()


class SandboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")

    def setUp(self):
        sign_in(self.client, self.budi)

    def sandbox_profile(self):
        return ConnectionProfile.objects.create(owner=self.budi, name="SBX", host="iot.example.org", port=443,
                                                path="/mqtt", platform_sandbox=True)

    @mock.patch("connections.platform_devices.platform.api_get")
    def test_list_and_create(self, api_get):
        api_get.side_effect = lambda request, path: SANDBOX if path.endswith("sandbox") else {
            "broker": BROKER, "devices": []}
        response = self.client.get(reverse("connections:platform"))
        self.assertContains(response, "MQTT sandbox")
        self.assertContains(response, "sandbox/budi/#")
        self.assertContains(response, "Create connection")

        response = self.client.post(reverse("connections:platform_sandbox"))
        profile = ConnectionProfile.objects.get(owner=self.budi, platform_sandbox=True)
        self.assertRedirects(response, reverse("connections:session", args=[profile.pk]))
        # Password sandbox tidak disimpan di profil.
        self.assertEqual((profile.url, profile.username), ("wss://iot.example.org:443/mqtt", ""))
        self.assertEqual([s.topic_filter for s in profile.subscriptions.all()], ["{sandbox}/#"])
        self.client.post(reverse("connections:platform_sandbox"))
        self.assertEqual(ConnectionProfile.objects.filter(platform_sandbox=True).count(), 1)

    @mock.patch("connections.platform_devices.platform.api_get")
    def test_list_without_sandbox_account_or_consent(self, api_get):
        devices = {"broker": BROKER, "devices": []}
        api_get.side_effect = lambda request, path: (
            {**SANDBOX, "enabled": False} if path.endswith("sandbox") else devices)
        self.assertContains(self.client.get(reverse("connections:platform")), "Create sandbox account on IoT Platform")
        response = self.client.post(reverse("connections:platform_sandbox"), follow=True)
        self.assertContains(response, "Create your MQTT sandbox account")

        def forbidden(request, path):
            if path.endswith("sandbox"):
                raise platform.PlatformForbidden("insufficient_scope")
            return devices
        api_get.side_effect = forbidden
        self.assertContains(self.client.get(reverse("connections:platform")), "Sign in again to allow")

    @mock.patch("connections.session.platform.api_get")
    def test_connect_with_sandbox_account(self, api_get):
        api_get.return_value = SANDBOX
        profile = self.sandbox_profile()
        profile.subscriptions.create(topic_filter="{sandbox}/#", qos=0)
        data = self.client.post(reverse("connections:connect", args=[profile.pk])).json()
        self.assertEqual((data["username"], data["password"], data["askPassword"]), ("sbx-5", "pw-sandbox", False))
        self.assertEqual(data["subscriptions"][0]["topic"], "sandbox/budi/#")
        self.assertEqual(data["sandbox"], {"root": "sandbox/budi", "shared": "sandbox/public"})
        api_get.assert_called_with(mock.ANY, "/api/v2/me/sandbox")

    @mock.patch("connections.session.platform.api_get")
    def test_connect_sandbox_errors(self, api_get):
        profile = self.sandbox_profile()
        url = reverse("connections:connect", args=[profile.pk])
        api_get.return_value = {**SANDBOX, "enabled": False}
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["manage"], SANDBOX["manage_url"])
        api_get.side_effect = platform.PlatformForbidden("x")
        self.assertIn("sign in again", self.client.post(url).json()["error"])
        api_get.side_effect = platform.PlatformUnavailable("x")
        self.assertEqual(self.client.post(url).status_code, 503)

    def test_session_page_hides_password_field(self):
        response = self.client.get(reverse("connections:session", args=[self.sandbox_profile().pk]))
        self.assertContains(response, "IoT Platform sandbox")
        self.assertNotContains(response, 'id="password"')


class SessionPageTests(TestCase):
    def test_automation_and_tabs_present(self):
        budi = User.objects.create(username="budi")
        self.client.force_login(budi)
        profile = ConnectionProfile.objects.create(owner=budi, name="EMQX", host="broker.emqx.io", port=8084,
                                                   path="/mqtt", protocol_version=5)
        response = self.client.get(reverse("connections:session", args=[profile.pk]))
        for element in ["repeat-toggle", "simulate-sensors", "auto-answer-template", "auto-ota-result",
                        "v5-properties", "prop-user", "topic-tree", "charts", "export-csv"]:
            self.assertContains(response, f'id="{element}"')
        self.assertContains(response, "{{method}}")            # placeholder tampil apa adanya
        self.assertEqual(response.context["config"]["protocolVersion"], 5)


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a test certificate")
class CustomCaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi")
        cls.pem = make_certificate()

    def setUp(self):
        self.client.force_login(self.budi)

    def test_ca_saved_only_for_mqtts(self):
        self.client.post(reverse("connections:create"), form_data(scheme="mqtts", port="", path="", ca_pem=self.pem))
        profile = ConnectionProfile.objects.get(owner=self.budi)
        self.assertIn("BEGIN CERTIFICATE", profile.ca_pem)
        self.client.post(reverse("connections:edit", args=[profile.pk]), form_data(ca_pem=self.pem))
        profile.refresh_from_db()
        self.assertEqual((profile.scheme, profile.ca_pem), ("wss", ""))       # wss: CA dari browser, kolom dikosongkan

    def test_invalid_ca_and_private_key_refused(self):
        response = self.client.post(reverse("connections:create"),
                                    form_data(scheme="mqtts", port="", path="", ca_pem="hello"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["ca_pem"])
        key = "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"
        response = self.client.post(reverse("connections:create"),
                                    form_data(scheme="mqtts", port="", path="", ca_pem=key))
        self.assertIn("private key", str(response.context["form"].errors["ca_pem"]).lower())
        self.assertFalse(ConnectionProfile.objects.exists())

    @override_settings(RELAY_PUBLIC_URL="wss://mqtt.example.org/relay/", RELAY_SHARED_SECRET=SECRET)
    def test_ca_goes_to_the_relay(self):
        profile = ConnectionProfile.objects.create(owner=self.budi, name="Lab", scheme="mqtts", host="broker.lab.org",
                                                   ca_pem=self.pem)
        data = self.client.post(reverse("connections:connect", args=[profile.pk])).json()
        ticket = RelayTicket.objects.get(pk=data["ticketId"])
        self.assertEqual(ticket.ca_pem, self.pem)
        redeemed = self.client.post(reverse("relay_redeem"), {"ticket": data["url"].rsplit("/", 1)[1]},
                                    content_type="application/json", headers={"X-Relay-Secret": SECRET}).json()
        self.assertEqual(redeemed["ca_pem"], self.pem)


class CleanupTests(TestCase):
    def test_old_tickets_deleted(self):
        from datetime import timedelta
        from io import StringIO

        from django.core.management import call_command
        from django.utils import timezone

        budi = User.objects.create(username="budi")
        profile = ConnectionProfile.objects.create(owner=budi, name="TCP", scheme="mqtt", host="broker.example.org")
        old, _ = RelayTicket.issue(budi, profile)
        RelayTicket.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        fresh, _ = RelayTicket.issue(budi, profile)
        out = StringIO()
        call_command("cleanup", stdout=out)
        self.assertEqual(list(RelayTicket.objects.values_list("pk", flat=True)), [fresh.pk])
        self.assertIn("Deleted 1 relay ticket", out.getvalue())
