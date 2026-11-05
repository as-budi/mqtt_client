"""Tahap M8: payload JSON di daftar pesan memakai penampil JSON IoT Platform."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import ConnectionProfile
from .tests_session import sign_in

STATIC = Path(settings.BASE_DIR) / "static"


class JsonViewerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.profile = ConnectionProfile.objects.create(owner=cls.budi, name="Lab", host="broker.example.org")

    def test_session_page_loads_viewer_before_session_script(self):
        sign_in(self.client, self.budi)
        html = self.client.get(reverse("connections:session", args=[self.profile.pk])).content.decode()
        self.assertIn("js/json_viewer.js", html)
        self.assertLess(html.index("js/json_viewer.js"), html.index("js/session.js"))

    def test_messages_use_viewer_and_keep_fold_state(self):
        script = (STATIC / "js" / "session.js").read_text()
        self.assertIn("JsonViewer.create(data, { toolbar: lines > JSON_TOOLBAR_LINES })", script)
        # Elemen pesan dipakai ulang saat daftar digambar ulang (lipatan tidak terbuka lagi).
        self.assertIn("if (message.element && message.elementKey === key) return message.element;", script)

    def test_viewer_and_styles_present(self):
        viewer = (STATIC / "js" / "json_viewer.js").read_text()
        self.assertIn("window.JsonViewer = { create, initAll };", viewer)
        self.assertIn("options.toolbar === false", viewer)
        css = (STATIC / "css" / "app.css").read_text()
        for rule in (".jv-line", ".jv-num", ".jv-toggle", ".jv-collapsed > .jv-children", ".message-json .jv-view"):
            self.assertIn(rule, css)
