"""Tahap M10: command yang sudah kedaluwarsa tidak dijawab oleh auto-responder."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC = Path(settings.BASE_DIR) / "static"
TEMPLATES = Path(settings.BASE_DIR) / "connections" / "templates" / "connections"


class CommandExpiryTests(SimpleTestCase):
    def test_auto_responder_skips_expired_commands(self):
        script = (STATIC / "js" / "session.js").read_text()
        self.assertIn("Date.now() / 1000 > expiresAt + CLOCK_TOLERANCE_S", script)
        # Diperiksa sebelum OTA disimulasikan dan sebelum command dijawab.
        check = script.index("if (commandExpired(data)) {")
        self.assertLess(check, script.index('if (method === "ota" && $("auto-ota").checked)'))
        self.assertLess(check, script.index('if ($("auto-answer").checked) {'))

    def test_session_page_has_info_line(self):
        self.assertIn('id="auto-command-info"', (TEMPLATES / "session.html").read_text())
