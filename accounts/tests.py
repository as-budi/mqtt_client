"""
Tes login lewat IoT Platform.

Platform TIDAK dihubungi sungguhan: klien OpenID Connect (Authlib) dan permintaan HTTP
ke platform diganti tiruan (unittest.mock). Alur sungguhan diuji manual dengan IoT
Platform di laptop (docs/tahap-m2-kerangka-dan-login.md bagian "Mencoba").
"""
import time
from unittest import mock

import requests
from authlib.integrations.base_client import OAuthError
from django.http import HttpResponseRedirect
from django.test import TestCase, override_settings
from django.urls import reverse

from . import platform
from .models import User
from .oidc import sync_user

CLAIMS = {"sub": "5", "preferred_username": "budi", "given_name": "Budi", "family_name": "Santoso",
          "email": "budi@example.com"}


def token(expires_in=600, **extra):
    return {"access_token": "AT1", "refresh_token": "RT1", "expires_in": expires_in, "expires_at":
            int(time.time()) + expires_in, "id_token": "ID1", "userinfo": dict(CLAIMS), **extra}


class FakeClient:
    """Pengganti klien Authlib: mencatat panggilan, tidak menghubungi platform."""

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
        self.authorize_calls, self.logout_calls = [], []

    def authorize_redirect(self, request, redirect_uri, **kwargs):
        self.authorize_calls.append((redirect_uri, kwargs))
        return HttpResponseRedirect("https://platform.example/o/authorize/?client_id=x")

    def authorize_access_token(self, request):
        if self.error:
            raise self.error
        return self.result

    def logout_redirect(self, request, **kwargs):
        self.logout_calls.append(kwargs)
        return HttpResponseRedirect("https://platform.example/o/logout/")


class LoginTests(TestCase):
    def patch_client(self, client):
        patcher = mock.patch("accounts.views.platform_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def sign_in(self, result=None):
        self.patch_client(FakeClient(result=result or token()))
        return self.client.get(reverse("accounts:callback"), {"code": "c", "state": "s"})

    def test_welcome_page(self):
        response = self.client.get(reverse("accounts:welcome"))
        self.assertContains(response, "Sign in with IoT Platform")
        self.assertContains(response, reverse("accounts:login") + "?signup=1")
        self.assertEqual(self.client.head(reverse("accounts:welcome")).status_code, 200)   # curl -I

    def test_pages_need_login(self):
        response = self.client.get(reverse("connections:list"))
        self.assertRedirects(response, reverse("accounts:welcome") + "?next=" + reverse("connections:list"))

    def test_login_redirects_to_platform_and_remembers_safe_next(self):
        client = self.patch_client(FakeClient())
        response = self.client.get(reverse("accounts:login"), {"next": "/connections/new/"})
        self.assertEqual(response["Location"], "https://platform.example/o/authorize/?client_id=x")
        redirect_uri, kwargs = client.authorize_calls[0]
        self.assertEqual(redirect_uri, "http://testserver/oidc/callback/")
        self.assertEqual(kwargs, {})
        self.assertEqual(self.client.session["login_next"], "/connections/new/")

        self.client.get(reverse("accounts:login"), {"next": "https://evil.example.com/", "signup": "1"})
        self.assertEqual(self.client.session["login_next"], "")
        self.assertEqual(client.authorize_calls[1][1], {"prompt": "create"})

    def test_callback_creates_user_and_stores_tokens(self):
        session = self.client.session
        session["login_next"] = "/connections/new/"
        session.save()
        response = self.sign_in()
        self.assertRedirects(response, "/connections/new/", fetch_redirect_response=False)
        user = User.objects.get(platform_sub="5")
        self.assertEqual((user.username, user.email, user.first_name), ("budi", "budi@example.com", "Budi"))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        stored = self.client.session[platform.SESSION_KEY]
        self.assertEqual((stored["access_token"], stored["refresh_token"], stored["id_token"]), ("AT1", "RT1", "ID1"))

    def test_next_login_updates_the_same_user(self):
        self.sign_in()
        self.client.logout()
        renamed = token(userinfo={**CLAIMS, "preferred_username": "budi.s", "email": "new@example.com"})
        self.sign_in(renamed)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().username, "budi.s")

    def test_username_clash_with_another_platform_user(self):
        User.objects.create(username="budi", platform_sub="99")      # pengguna lama yang ganti nama di platform
        user = sync_user(CLAIMS)
        self.assertEqual(user.username, "budi")
        self.assertEqual(User.objects.get(platform_sub="99").username, "budi~99")

    def test_canceled_and_failed_sign_in(self):
        self.patch_client(FakeClient(error=OAuthError(error="access_denied")))
        response = self.client.get(reverse("accounts:callback"), {"error": "access_denied"}, follow=True)
        self.assertContains(response, "Sign-in was canceled.")
        self.patch_client(FakeClient(error=OAuthError(error="mismatching_state")))
        # assertLogs: pesan log yang memang diharapkan tidak dicetak ke layar saat tes.
        with self.assertLogs("accounts.views", "WARNING") as logs:
            response = self.client.get(reverse("accounts:callback"), follow=True)
        self.assertIn("mismatching_state", logs.output[0])
        self.assertContains(response, "Sign-in with IoT Platform failed.")
        self.assertFalse(User.objects.exists())

    def test_platform_unreachable_on_login(self):
        client = FakeClient()
        client.authorize_redirect = mock.Mock(side_effect=requests.ConnectionError("down"))
        self.patch_client(client)
        with self.assertLogs("accounts.views", "ERROR"):
            response = self.client.get(reverse("accounts:login"), follow=True)
        self.assertContains(response, "IoT Platform cannot be reached")

    @mock.patch("accounts.platform.requests.post")
    @mock.patch("accounts.platform._endpoint", return_value="https://platform.example/o/revoke_token/")
    def test_sign_out_revokes_the_refresh_token(self, _endpoint, post):
        self.sign_in()
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:welcome"))
        self.assertEqual(post.call_args.kwargs["data"]["token"], "RT1")
        self.assertNotIn("_auth_user_id", self.client.session)

    @mock.patch("accounts.platform.requests.post")
    @mock.patch("accounts.platform._endpoint", return_value="https://platform.example/o/revoke_token/")
    def test_sign_out_of_platform_too(self, _endpoint, post):
        self.sign_in()
        client = self.patch_client(FakeClient())
        response = self.client.post(reverse("accounts:logout"), {"platform": "1"})
        self.assertEqual(response["Location"], "https://platform.example/o/logout/")
        self.assertEqual(client.logout_calls[0]["id_token_hint"], "ID1")
        self.assertEqual(client.logout_calls[0]["post_logout_redirect_uri"], "http://testserver/")


@mock.patch("accounts.platform._endpoint", return_value="https://platform.example/o/token/")
class PlatformSessionTests(TestCase):
    """Middleware: access token kedaluwarsa diperbarui; ditolak -> logout."""

    def setUp(self):
        self.user = User.objects.create(username="budi", platform_sub="5")
        self.client.force_login(self.user)
        session = self.client.session
        session[platform.SESSION_KEY] = {"access_token": "OLD", "refresh_token": "RT1",
                                         "expires_at": int(time.time()) - 5, "id_token": "ID1"}
        session.save()

    def respond(self, status, body=None):
        response = mock.Mock(status_code=status, text=str(body))
        response.json.return_value = body
        return response

    def test_expired_token_is_refreshed(self, _endpoint):
        new = {"access_token": "NEW", "refresh_token": "RT2", "expires_in": 600}
        with mock.patch("accounts.platform.requests.post", return_value=self.respond(200, new)) as post:
            response = self.client.get(reverse("connections:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args.kwargs["data"]["refresh_token"], "RT1")
        stored = self.client.session[platform.SESSION_KEY]
        self.assertEqual((stored["access_token"], stored["refresh_token"], stored["id_token"]), ("NEW", "RT2", "ID1"))

    def test_refused_refresh_signs_the_user_out(self, _endpoint):
        with mock.patch("accounts.platform.requests.post", return_value=self.respond(400, {"error": "invalid_grant"})):
            response = self.client.get(reverse("connections:list"), follow=True)
        self.assertContains(response, "Your IoT Platform session has ended")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_platform_down_keeps_the_user_signed_in(self, _endpoint):
        with mock.patch("accounts.platform.requests.post", side_effect=requests.ConnectionError("down")) as post:
            self.assertEqual(self.client.get(reverse("connections:list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("connections:list")).status_code, 200)
        self.assertEqual(post.call_count, 1)        # dicoba lagi paling cepat 60 detik kemudian

    def test_valid_token_is_not_refreshed(self, _endpoint):
        session = self.client.session
        session[platform.SESSION_KEY]["expires_at"] = int(time.time()) + 600
        session.save()
        with mock.patch("accounts.platform.requests.post") as post:
            self.client.get(reverse("connections:list"))
        post.assert_not_called()

    def test_local_admin_without_platform_account_is_left_alone(self, _endpoint):
        admin = User.objects.create_superuser("root", password="rahasia-12345")
        self.client.force_login(admin)
        with mock.patch("accounts.platform.requests.post") as post:
            self.assertEqual(self.client.get(reverse("connections:list")).status_code, 200)
        post.assert_not_called()

    def test_api_get_uses_bearer_token(self, _endpoint):
        session = self.client.session
        session[platform.SESSION_KEY]["expires_at"] = int(time.time()) + 600
        session.save()
        request = mock.Mock(session=self.client.session)
        with override_settings(PLATFORM_URL="https://platform.example"), \
                mock.patch("accounts.platform.requests.get", return_value=self.respond(200, {"id": 5})) as get:
            self.assertEqual(platform.api_get(request, "/api/v2/me"), {"id": 5})
        self.assertEqual(get.call_args.args[0], "https://platform.example/api/v2/me")
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer OLD"})
        with mock.patch("accounts.platform.requests.get", return_value=self.respond(401)), \
                self.assertRaises(platform.PlatformSessionEnded):
            platform.api_get(request, "/api/v2/me")
