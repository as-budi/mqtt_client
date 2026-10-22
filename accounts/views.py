"""
Halaman depan, login lewat IoT Platform, dan logout.

    GET  /                 halaman depan: "Sign in with IoT Platform" / "Create account"
    GET  /login/           mulai login (?signup=1 = langsung ke Sign up platform; ?next=...)
    GET  /oidc/callback/   platform mengembalikan pengguna ke sini dengan ?code=&state=
    POST /logout/          keluar dari aplikasi ini (platform=1: dari IoT Platform juga)
"""
import logging

import requests
from authlib.integrations.base_client import OAuthError
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import platform
from .oidc import platform_client, sync_user

logger = logging.getLogger(__name__)
NEXT_KEY = "login_next"


def safe_next(request, url):
    """Hanya alamat di aplikasi ini (mencegah open redirect)."""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return url
    return ""


@require_GET
def welcome(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, "accounts/welcome.html", {"next": safe_next(request, request.GET.get("next", ""))})


@require_GET
def login_start(request):
    """Simpan tujuan setelah login, lalu alihkan browser ke halaman login platform."""
    request.session[NEXT_KEY] = safe_next(request, request.GET.get("next", ""))
    extra = {}
    if request.GET.get("signup"):
        # OpenID Connect "prompt=create": platform menampilkan Sign up, bukan Log in.
        extra["prompt"] = "create"
    redirect_uri = request.build_absolute_uri(reverse("accounts:callback"))
    try:
        return platform_client().authorize_redirect(request, redirect_uri, **extra)
    except requests.RequestException:
        logger.exception("IoT Platform discovery failed")
        messages.error(request, "IoT Platform cannot be reached right now. Please try again in a moment.")
        return redirect("accounts:welcome")


@require_GET
def callback(request):
    try:
        token = platform_client().authorize_access_token(request)
    except OAuthError as exc:
        if exc.error == "access_denied":
            messages.info(request, "Sign-in was canceled.")
        else:
            logger.warning("OIDC callback failed: %s %s", exc.error, exc.description)
            messages.error(request, "Sign-in with IoT Platform failed. Please try again.")
        return redirect("accounts:welcome")
    except requests.RequestException:
        logger.exception("IoT Platform token request failed")
        messages.error(request, "IoT Platform cannot be reached right now. Please try again in a moment.")
        return redirect("accounts:welcome")

    claims = token.get("userinfo")
    if not claims or not claims.get("sub"):
        messages.error(request, "IoT Platform did not identify the user.")
        return redirect("accounts:welcome")

    next_url = request.session.pop(NEXT_KEY, "")
    user = sync_user(claims)
    # login() mengganti id sesi (mencegah session fixation); isi sesi lama tetap terbawa.
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    platform.save_token(request, token)
    messages.success(request, f"Signed in as {user.username}.")
    return redirect(next_url or settings.LOGIN_REDIRECT_URL)


@require_POST
def logout_view(request):
    """Keluar. Refresh token di platform dicabut supaya tidak bisa dipakai lagi.

    platform=1: setelah itu ke halaman logout IoT Platform juga (RP-initiated logout),
    yang lalu mengembalikan pengguna ke halaman depan aplikasi ini.
    """
    everywhere = request.POST.get("platform") == "1"
    id_token = (platform.stored_token(request) or {}).get("id_token", "")
    platform.revoke(request)
    logout(request)
    if everywhere and id_token:
        try:
            return platform_client().logout_redirect(
                request,
                post_logout_redirect_uri=request.build_absolute_uri(reverse("accounts:welcome")),
                id_token_hint=id_token,
            )
        except (requests.RequestException, RuntimeError):
            logger.exception("IoT Platform logout redirect failed")
    messages.info(request, "You have signed out.")
    return redirect("accounts:welcome")
