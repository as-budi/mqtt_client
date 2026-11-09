"""Tes tahap M12: gaya tampilan Standard / FILKOM."""
from django.test import TestCase, override_settings
from django.urls import reverse

from connections.tests_session import sign_in

from .models import User


class UiStyleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.budi = User.objects.create(username="budi", platform_sub="5")

    def page(self):
        return self.client.get(reverse("connections:list"))

    def test_default_is_standard_and_choice_is_saved(self):
        sign_in(self.client, self.budi)
        page = self.page()
        self.assertContains(page, 'data-ui="standard"')
        self.assertNotContains(page, "css/filkom.css")
        self.assertContains(page, 'class="ui-style-switch')
        response = self.client.post(reverse("accounts:ui_style"), {"style": "filkom", "next": "/connections/"})
        self.assertRedirects(response, "/connections/", fetch_redirect_response=False)
        self.budi.refresh_from_db()
        self.assertEqual(self.budi.ui_style, "filkom")
        page = self.page()
        self.assertContains(page, 'data-ui="filkom"')
        self.assertContains(page, "css/filkom.css")
        self.assertContains(page, "family=Roboto")

    def test_bad_values_and_open_redirect(self):
        sign_in(self.client, self.budi)
        response = self.client.post(reverse("accounts:ui_style"), {"style": "pink", "next": "https://evil.example/"})
        self.assertRedirects(response, reverse("connections:list"), fetch_redirect_response=False)
        self.budi.refresh_from_db()
        self.assertEqual(self.budi.ui_style, "")
        self.assertEqual(self.client.get(reverse("accounts:ui_style")).status_code, 405)

    @override_settings(UI_STYLE="filkom")
    def test_site_default_for_visitors(self):
        self.assertContains(self.client.get(reverse("accounts:welcome")), 'data-ui="filkom"')

    @override_settings(UI_STYLE="standard", UI_STYLE_SELECTABLE=False)
    def test_locked_style(self):
        self.budi.ui_style = "filkom"
        self.budi.save()
        sign_in(self.client, self.budi)
        page = self.page()
        self.assertContains(page, 'data-ui="standard"')
        self.assertNotContains(page, "ui-style-switch")
        self.client.post(reverse("accounts:ui_style"), {"style": "standard"})
        self.budi.refresh_from_db()
        self.assertEqual(self.budi.ui_style, "filkom")       # tidak berubah saat dikunci
