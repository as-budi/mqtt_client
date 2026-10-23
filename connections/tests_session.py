"""Tes halaman koneksi, bahan connect, saved messages, device platform (M3), dan tiket relay (M4)."""
import json
import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import platform
from accounts.models import User

from .models import ConnectionProfile, RelayTicket, SavedMessage, SubscriptionPreset

SECRET = "s" * 40
BROKER = {"mqtt": {"host": "iot.example.org", "port": 8883, "tls": True},
          "websocket": "wss://iot.example.org/mqtt", "device_login": True, "topic_prefix": "iot"}


def sign_in(client, user):
    """Login seperti setelah OIDC: termasuk token platform yang masih berlaku di sesi."""
    client.force_login(user)
    session = client.session
    session[platform.SESSION_KEY] = {"access_token": "AT", "refresh_token": "RT",
                                     "expires_at": int(time.time()) + 600, "id_token": "ID"}
    session.save()


def device(id_, token="TOKEN123", name="Greenhouse"):
    topics = {"telemetry": f"iot/{token}/telemetry", "status": f"iot/{token}/status"} if token else None
    return {"id": id_, "name": name, "location": None, "owner": "budi", "role": "owner" if token else "viewer",
            "is_active": True, "is_online": False, "access_token": token, "topics": topics, "variables": []}


class SessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.siti = User.objects.create(username="siti")
        cls.direct = ConnectionProfile.objects.create(
            owner=cls.budi, name="EMQX", host="broker.emqx.io", port=8084, path="/mqtt", username="student",
            will_topic="lab/budi/status", will_payload="offline", will_retain=True)
        SubscriptionPreset.objects.create(profile=cls.direct, topic_filter="lab/#", qos=1)
        cls.relay = ConnectionProfile.objects.create(owner=cls.budi, name="TCP", scheme="mqtts", host="broker.example.org")
        cls.device = ConnectionProfile.objects.create(owner=cls.budi, name="Dev", host="iot.example.org", port=443,
                                                      platform_device_id=7)
        SubscriptionPreset.objects.create(profile=cls.device, topic_filter="{prefix}/{token}/desired", qos=1)

    def setUp(self):
        sign_in(self.client, self.budi)

    def connect(self, profile):
        return self.client.post(reverse("connections:connect", args=[profile.pk]))

    def test_session_page(self):
        response = self.client.get(reverse("connections:session", args=[self.direct.pk]))
        self.assertContains(response, "vendor/mqtt.min.js")
        self.assertContains(response, 'id="password"')          # profil dengan username: password diketik
        config = response.context["config"]
        self.assertEqual(config["url"], "wss://broker.emqx.io:8084/mqtt")
        self.assertEqual(config["subscriptions"][0]["topic"], "lab/#")
        other = ConnectionProfile.objects.create(owner=self.siti, name="X", host="example.org")
        self.assertEqual(self.client.get(reverse("connections:session", args=[other.pk])).status_code, 404)

    def test_connect_direct(self):
        data = self.connect(self.direct).json()
        self.assertEqual((data["route"], data["url"]), ("direct", "wss://broker.emqx.io:8084/mqtt"))
        self.assertTrue(data["clientId"].startswith("mqttc-"))
        self.assertNotEqual(data["clientId"], self.connect(self.direct).json()["clientId"])
        self.assertEqual((data["username"], data["password"], data["askPassword"]), ("student", None, True))
        self.assertEqual(data["subscriptions"], [{"topic": "lab/#", "qos": 1, "color": "gray", "muted": False}])
        self.assertEqual(data["options"]["will"], {"topic": "lab/budi/status", "payload": "offline",
                                                   "qos": 0, "retain": True})
        self.assertEqual(self.client.get(reverse("connections:connect", args=[self.direct.pk])).status_code, 405)

    @mock.patch("connections.session.platform.api_get")
    def test_connect_as_platform_device(self, api_get):
        api_get.return_value = {"broker": BROKER, "devices": [device(7)]}
        data = self.connect(self.device).json()
        self.assertEqual((data["username"], data["password"], data["askPassword"]), ("TOKEN123", "TOKEN123", False))
        self.assertEqual(data["subscriptions"][0]["topic"], "iot/TOKEN123/desired")
        self.assertEqual(data["topics"]["telemetry"], "iot/TOKEN123/telemetry")
        api_get.assert_called_with(mock.ANY, "/api/v2/me/devices")

    @mock.patch("connections.session.platform.api_get")
    def test_connect_as_platform_device_errors(self, api_get):
        api_get.return_value = {"broker": BROKER, "devices": []}
        self.assertEqual(self.connect(self.device).status_code, 403)
        api_get.return_value = {"broker": BROKER, "devices": [device(7, token=None)]}
        self.assertIn("Editor", self.connect(self.device).json()["error"])
        api_get.side_effect = platform.PlatformSessionEnded("x")
        response = self.connect(self.device)
        self.assertEqual((response.status_code, response.json()["signin"]), (401, reverse("accounts:login")))
        api_get.side_effect = platform.PlatformUnavailable("x")
        self.assertEqual(self.connect(self.device).status_code, 503)

    @override_settings(RELAY_PUBLIC_URL="")
    def test_relay_disabled(self):
        response = self.connect(self.relay)
        self.assertEqual(response.status_code, 503)
        self.assertIn("no relay", response.json()["error"])

    @override_settings(RELAY_PUBLIC_URL="wss://mqtt.example.org/relay/", RELAY_TICKETS_PER_MINUTE=2)
    def test_relay_ticket(self):
        data = self.connect(self.relay).json()
        token = data["url"].rsplit("/", 1)[1]
        self.assertTrue(data["url"].startswith("wss://mqtt.example.org/relay/"))
        ticket = RelayTicket.objects.get(pk=data["ticketId"])
        self.assertEqual((ticket.host, ticket.port, ticket.tls, ticket.user), ("broker.example.org", 8883, True, self.budi))
        self.assertEqual(ticket.token_hash, RelayTicket.hash(token))
        self.assertNotIn(token, ticket.token_hash)              # hanya hash yang disimpan
        self.connect(self.relay)
        self.assertEqual(self.connect(self.relay).status_code, 429)


@override_settings(RELAY_SHARED_SECRET=SECRET, RELAY_TICKET_SECONDS=60)
class RelayApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi")
        cls.profile = ConnectionProfile.objects.create(owner=cls.budi, name="TCP", scheme="mqtt",
                                                       host="broker.hivemq.com")

    def redeem(self, token, secret=SECRET, **headers):
        return self.client.post(reverse("relay_redeem"), json.dumps({"ticket": token}), content_type="application/json",
                                HTTP_X_RELAY_SECRET=secret, **headers)

    def test_redeem_once(self):
        ticket, token = RelayTicket.issue(self.budi, self.profile)
        response = self.redeem(token)
        self.assertEqual(response.json(), {"ticket_id": ticket.pk, "user_id": self.budi.pk, "username": "budi",
                                           "host": "broker.hivemq.com", "port": 1883, "tls": False,
                                           "ca_pem": ""})
        self.assertEqual(self.redeem(token).status_code, 404)

    def test_redeem_is_protected(self):
        _, token = RelayTicket.issue(self.budi, self.profile)
        self.assertEqual(self.redeem(token, secret="wrong").status_code, 404)
        # Lewat Nginx (ada X-Forwarded-For) selalu ditolak, walaupun rahasianya benar.
        self.assertEqual(self.redeem(token, HTTP_X_FORWARDED_FOR="203.0.113.5").status_code, 404)
        self.assertEqual(self.redeem(token).status_code, 200)

    def test_expired_ticket_and_inactive_user(self):
        ticket, token = RelayTicket.issue(self.budi, self.profile)
        RelayTicket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(seconds=61))
        self.assertEqual(self.redeem(token).status_code, 404)
        _, token = RelayTicket.issue(self.budi, self.profile)
        User.objects.filter(pk=self.budi.pk).update(is_active=False)
        self.assertEqual(self.redeem(token).status_code, 404)

    def test_report_and_status(self):
        ticket, token = RelayTicket.issue(self.budi, self.profile)
        response = self.client.post(reverse("relay_report"), json.dumps({
            "ticket": token, "failure": "address_not_allowed", "detail": "port 22 is not allowed"}),
            content_type="application/json", HTTP_X_RELAY_SECRET=SECRET)
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.budi)
        data = self.client.get(reverse("connections:relay_status", args=[ticket.pk])).json()
        self.assertEqual(data["failure"], "address_not_allowed")
        self.assertIn("private networks", data["message"])
        self.assertEqual(data["detail"], "port 22 is not allowed")
        self.client.force_login(User.objects.create(username="other"))
        self.assertEqual(self.client.get(reverse("connections:relay_status", args=[ticket.pk])).status_code, 404)


class SavedMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi")
        cls.a = ConnectionProfile.objects.create(owner=cls.budi, name="A", host="broker.emqx.io")
        cls.b = ConnectionProfile.objects.create(owner=cls.budi, name="B", host="broker.emqx.io")

    def setUp(self):
        self.client.force_login(self.budi)

    def save(self, profile, **data):
        body = {"name": "Temp", "topic": "lab/temp", "payload": "21", "qos": 1, "retain": False, **data}
        return self.client.post(reverse("connections:saved", args=[profile.pk]), json.dumps(body),
                                content_type="application/json")

    def test_save_list_delete(self):
        self.assertEqual(self.save(self.a).status_code, 201)
        self.assertEqual(self.save(self.a, name="Everywhere", allConnections=True).status_code, 201)
        names = [m["name"] for m in self.client.get(reverse("connections:saved", args=[self.b.pk])).json()["messages"]]
        self.assertEqual(names, ["Everywhere"])           # "Temp" hanya untuk koneksi A
        message = SavedMessage.objects.get(name="Temp")
        self.assertEqual(self.client.post(reverse("connections:saved_delete", args=[message.pk])).status_code, 200)
        self.client.force_login(User.objects.create(username="other"))
        other = SavedMessage.objects.get(name="Everywhere")
        self.assertEqual(self.client.post(reverse("connections:saved_delete", args=[other.pk])).status_code, 404)

    def test_wildcard_topic_refused(self):
        response = self.save(self.a, topic="lab/#")
        self.assertEqual(response.status_code, 400)
        self.assertIn("wildcards", response.json()["error"])


class PlatformDeviceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")

    def setUp(self):
        sign_in(self.client, self.budi)
        patcher = mock.patch("connections.platform_devices.platform.api_get")
        self.api_get = patcher.start()
        self.addCleanup(patcher.stop)
        self.api_get.return_value = {"broker": BROKER, "devices": [device(7), device(8, token=None, name="Shared")]}

    def test_list(self):
        response = self.client.get(reverse("connections:platform"))
        self.assertContains(response, "Greenhouse")
        self.assertContains(response, "Needs Editor access")
        self.assertContains(response, "wss://iot.example.org/mqtt")

    def test_create_profile_for_device(self):
        response = self.client.post(reverse("connections:platform_create", args=[7]))
        profile = ConnectionProfile.objects.get(owner=self.budi, platform_device_id=7)
        self.assertRedirects(response, reverse("connections:session", args=[profile.pk]))
        self.assertEqual(profile.url, "wss://iot.example.org:443/mqtt")
        self.assertEqual(profile.username, "")                  # token tidak disimpan
        self.assertEqual([s.topic_filter for s in profile.subscriptions.all()],
                         ["{prefix}/{token}/desired", "{prefix}/{token}/commands/+", "{prefix}/{token}/errors"])
        # Kedua kali: profil yang sama dibuka, tidak dibuat lagi.
        self.client.post(reverse("connections:platform_create", args=[7]))
        self.assertEqual(ConnectionProfile.objects.filter(platform_device_id=7).count(), 1)

    def test_tcp_broker_when_platform_has_no_websocket(self):
        self.api_get.return_value = {"broker": {**BROKER, "websocket": None}, "devices": [device(7)]}
        self.client.post(reverse("connections:platform_create", args=[7]))
        self.assertEqual(ConnectionProfile.objects.get(platform_device_id=7).url, "mqtts://iot.example.org:8883")

    def test_viewer_cannot_create(self):
        response = self.client.post(reverse("connections:platform_create", args=[8]), follow=True)
        self.assertContains(response, "You need Editor access")
        self.assertFalse(ConnectionProfile.objects.exists())

    def test_platform_session_ended(self):
        self.api_get.side_effect = platform.PlatformSessionEnded("x")
        response = self.client.get(reverse("connections:platform"))
        self.assertRedirects(response, reverse("accounts:welcome"))
