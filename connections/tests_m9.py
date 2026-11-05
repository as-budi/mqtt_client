"""Tahap M9: payload JSON di kartu Publish tampil seperti code editor."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import ConnectionProfile
from .tests_session import sign_in

STATIC = Path(settings.BASE_DIR) / "static"


class PayloadEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")
        cls.profile = ConnectionProfile.objects.create(owner=cls.budi, name="Lab", host="broker.example.org")

    def test_scripts_load_in_order(self):
        sign_in(self.client, self.budi)
        html = self.client.get(reverse("connections:session", args=[self.profile.pk])).content.decode()
        order = [html.index(name) for name in ("js/json_viewer.js", "js/payload_editor.js", "js/session.js")]
        self.assertEqual(order, sorted(order))
        self.assertIn('id="publish-format"', html)

    def test_editor_follows_json_format(self):
        script = (STATIC / "js" / "session.js").read_text()
        self.assertIn('PayloadEditor.attach($("publish-payload")', script)
        self.assertIn('isJson: () => $("publish-format").value === "json"', script)
        # Setiap perubahan lewat kode (fillPublish, Format, ganti format) melewati checkPayload().
        self.assertIn("if (payloadEditor) payloadEditor.refresh();", script)

    def test_editor_script_and_styles(self):
        editor = (STATIC / "js" / "payload_editor.js").read_text()
        self.assertIn("window.PayloadEditor = { attach, highlight };", editor)
        self.assertIn("window.JsonViewer.create(data)", editor)          # tab Preview berlipat
        self.assertIn("escapeHtml", editor)                              # isi tidak pernah jadi HTML
        css = (STATIC / "css" / "app.css").read_text()
        for rule in (".pe-active .pe-gutter", ".pe-active .pe-highlight", ".pe-active textarea", ".pe-ph"):
            self.assertIn(rule, css)
