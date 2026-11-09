"""Tes tahap M13: dokumentasi pengguna MQTT Client."""
import re

from django.test import TestCase
from django.urls import reverse

from . import pages, search


class DocsTests(TestCase):
    def setUp(self):
        search._index.clear()

    def test_index_lists_every_page_without_login(self):
        response = self.client.get(reverse("userdocs:index"))
        self.assertEqual(response.status_code, 200)
        for page in pages.PAGES:
            self.assertContains(response, reverse("userdocs:page", args=[page.slug]))
        self.assertContains(response, "Section Navigation")
        self.assertContains(response, "Sign in with IoT Platform")

    def test_every_page_renders_with_headings_and_neighbours(self):
        for page in pages.PAGES:
            response = self.client.get(reverse("userdocs:page", args=[page.slug]))
            self.assertEqual(response.status_code, 200, page.slug)
            html = response.content.decode()
            self.assertIn(f"<h1 class=\"h3\">{page.title}</h1>", html)
            self.assertTrue(re.search(r'<h2 id="[a-z0-9-]+"', html), page.slug)
        self.assertEqual(self.client.get(reverse("userdocs:page", args=["nope"])).status_code, 404)

    def test_placeholders_are_shown_literally(self):
        html = self.client.get(reverse("userdocs:page", args=["subscribe-publish"])).content.decode()
        self.assertIn("{{random:20:30}}", html)

    def test_search(self):
        response = self.client.get(reverse("userdocs:search"), {"q": "retained"})
        self.assertContains(response, "result")
        self.assertContains(response, reverse("userdocs:page", args=["mqtt-basics"]) + "#retained")
        self.assertContains(self.client.get(reverse("userdocs:search"), {"q": "zzqqxx"}), "Nothing matches")

    def test_link_in_top_bar(self):
        self.assertContains(self.client.get(reverse("accounts:welcome")), reverse("userdocs:index"))


class FaviconTests(TestCase):
    def test_icons_follow_the_style(self):
        page = self.client.get(reverse("accounts:welcome"))
        self.assertContains(page, "img/favicon-standard.svg")
        self.assertContains(page, "img/apple-touch-icon-standard.png")
        with self.settings(UI_STYLE="filkom"):
            self.assertContains(self.client.get(reverse("accounts:welcome")), "img/favicon-filkom.svg")
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("img/favicon.ico"))
