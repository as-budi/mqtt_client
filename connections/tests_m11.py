"""Tes tahap M11: simulasi kamera, proxy unggahan snapshot ke IoT Platform."""
from unittest import mock

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import platform
from accounts.models import User

from .models import ConnectionProfile
from .tests_session import BROKER, device, sign_in

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"\xff\xd9"


def answer(status, data):
    response = mock.Mock(status_code=status)
    response.json.return_value = data
    return response


@override_settings(PLATFORM_URL="https://iot.example.org", SNAPSHOT_PROXY_MAX_KB=1, SNAPSHOT_PROXY_PER_MINUTE=0)
class SnapshotProxyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.siti = User.objects.create(username="siti")
        cls.profile = ConnectionProfile.objects.create(owner=cls.budi, name="Cam", host="iot.example.org", port=443,
                                                       platform_device_id=7)
        cls.plain = ConnectionProfile.objects.create(owner=cls.budi, name="EMQX", host="broker.emqx.io")

    def setUp(self):
        cache.clear()
        sign_in(self.client, self.budi)
        patcher = mock.patch("connections.session.platform.api_get",
                             return_value={"broker": BROKER, "devices": [device(7)]})
        self.api_get = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, profile=None, body=JPEG, content_type="image/jpeg", **headers):
        return self.client.post(reverse("connections:snapshot", args=[(profile or self.profile).pk]), data=body,
                                content_type=content_type,
                                **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()})

    @mock.patch("connections.snapshot.requests.post")
    def test_forwards_to_the_platform(self, post):
        post.return_value = answer(201, {"id": 118, "size": len(JPEG), "width": 640, "height": 480})
        response = self.post(x_command_id="42", x_source="command", x_camera="ignored")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], 118)
        url = post.call_args[0][0]
        self.assertEqual(url, "https://iot.example.org/api/v1/TOKEN123/snapshot")
        self.assertEqual(post.call_args[1]["data"], JPEG)
        self.assertEqual(post.call_args[1]["headers"],
                         {"Content-Type": "image/jpeg", "X-Command-Id": "42", "X-Source": "command"})
        # Alamat disimpan sebentar: unggahan berikutnya tidak memanggil API device lagi.
        self.post(x_source="periodic")
        self.assertEqual(self.api_get.call_count, 1)

    @mock.patch("connections.snapshot.requests.post")
    def test_snapshot_url_from_the_platform_is_preferred(self, post):
        item = {**device(7), "snapshot_url": "https://iot.example.org/custom/snapshot"}
        self.api_get.return_value = {"broker": BROKER, "devices": [item]}
        post.return_value = answer(201, {"id": 1})
        self.post()
        self.assertEqual(post.call_args[0][0], "https://iot.example.org/custom/snapshot")

    @mock.patch("connections.snapshot.requests.post")
    def test_platform_errors_are_passed_on(self, post):
        for status, message in ((413, "too large"), (415, "not a JPEG"), (429, "too many")):
            post.return_value = answer(status, {"error": message})
            response = self.post()
            self.assertEqual((response.status_code, response.json()["error"]), (status, message))
        post.side_effect = requests.ConnectionError("down")
        self.assertEqual(self.post().status_code, 503)

    @mock.patch("connections.snapshot.requests.post")
    def test_local_checks(self, post):
        self.assertEqual(self.post(body=b"x" * 2048).status_code, 413)          # > SNAPSHOT_PROXY_MAX_KB
        self.assertEqual(self.post(content_type="text/plain").status_code, 415)
        self.assertEqual(self.post(body=b"").status_code, 400)
        self.assertEqual(self.post(profile=self.plain).status_code, 400)        # bukan device platform
        other = ConnectionProfile.objects.create(owner=self.siti, name="X", host="x.org", platform_device_id=7)
        self.assertEqual(self.post(profile=other).status_code, 404)
        self.assertEqual(self.client.get(reverse("connections:snapshot", args=[self.profile.pk])).status_code, 405)
        post.assert_not_called()

    @override_settings(SNAPSHOT_PROXY_PER_MINUTE=3)
    @mock.patch("connections.snapshot.requests.post")
    def test_rate_limit(self, post):
        post.return_value = answer(201, {"id": 1})
        codes = [self.post().status_code for _ in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])

    def test_device_and_session_problems(self):
        self.api_get.return_value = {"broker": BROKER, "devices": [device(7, token=None)]}
        self.assertEqual(self.post().status_code, 403)                          # Viewer: tanpa token
        self.api_get.return_value = {"broker": BROKER, "devices": []}
        self.assertEqual(self.post().status_code, 403)                          # device tidak ada lagi
        self.api_get.side_effect = platform.PlatformSessionEnded("x")
        response = self.post()
        self.assertEqual(response.status_code, 401)
        self.assertIn("signin", response.json())
        self.api_get.side_effect = platform.PlatformUnavailable("x")
        self.assertEqual(self.post().status_code, 503)

    @mock.patch("connections.snapshot.requests.post")
    def test_new_token_after_401(self, post):
        post.return_value = answer(401, {"error": "Invalid access token."})
        self.assertEqual(self.post().status_code, 401)
        post.return_value = answer(201, {"id": 2})
        self.post()
        self.assertEqual(self.api_get.call_count, 2)                            # alamat lama dilupakan

    def test_session_page_has_the_camera_simulator(self):
        page = self.client.get(reverse("connections:session", args=[self.profile.pk]))
        self.assertContains(page, 'id="camera-sim"')
        self.assertContains(page, "js/camera_sim.js")
        config = page.context["config"]
        self.assertEqual(config["urls"]["snapshot"], reverse("connections:snapshot", args=[self.profile.pk]))
        self.assertEqual(config["urls"]["gallery"], "https://iot.example.org/cameras/devices/7/")
        plain = self.client.get(reverse("connections:session", args=[self.plain.pk])).context["config"]
        self.assertIsNone(plain["urls"]["gallery"])
