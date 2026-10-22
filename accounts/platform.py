"""
Token IoT Platform milik pengguna yang sedang login, dan pemanggilan API platform.

Setelah login, token disimpan di SESI SERVER (tabel django_session), tidak pernah
dikirim ke JavaScript atau ditulis di cookie:

    session["platform_token"] = {
        "access_token":  "...",   # kartu akses API platform, berlaku 10 menit
        "refresh_token": "...",   # untuk meminta access token baru, BERGANTI tiap dipakai
        "expires_at":    1761030000,
        "id_token":      "...",   # dipakai saat "log out of IoT Platform too"
    }

Access token kedaluwarsa -> diperbarui dengan refresh token (refresh()). Bila platform
MENOLAK (izin dicabut di Connected apps, akun dinonaktifkan, refresh token dipakai ulang),
pengguna harus login lagi: PlatformSessionEnded. Bila platform tidak bisa dihubungi
(jaringan), sesi dibiarkan: PlatformUnavailable.
"""
import time

import requests
from django.conf import settings

from .oidc import platform_client

SESSION_KEY = "platform_token"
# Perbarui sedikit sebelum benar-benar kedaluwarsa, supaya token tidak habis di tengah jalan.
REFRESH_MARGIN = 30


class PlatformSessionEnded(Exception):
    """Platform menolak token: pengguna harus login lagi."""


class PlatformUnavailable(Exception):
    """Platform tidak bisa dihubungi atau menjawab error server."""


def save_token(request, token):
    expires_at = token.get("expires_at") or int(time.time()) + int(token.get("expires_in", 0))
    old = request.session.get(SESSION_KEY, {})
    request.session[SESSION_KEY] = {
        "access_token": token["access_token"],
        # Respons refresh tidak selalu membawa id_token: pakai yang lama.
        "refresh_token": token.get("refresh_token", old.get("refresh_token", "")),
        "expires_at": int(expires_at),
        "id_token": token.get("id_token", old.get("id_token", "")),
    }


def stored_token(request):
    return request.session.get(SESSION_KEY)


def is_expired(token, now=None):
    return (now or time.time()) >= token["expires_at"] - REFRESH_MARGIN


def _endpoint(name, fallback):
    try:
        metadata = platform_client().load_server_metadata()
    except requests.RequestException as exc:
        raise PlatformUnavailable(str(exc)) from exc
    return metadata.get(name) or f"{settings.OIDC_ISSUER}/{fallback}"


def refresh(request):
    """Tukar refresh token dengan access token baru (dan refresh token baru)."""
    token = stored_token(request)
    if not token or not token.get("refresh_token"):
        raise PlatformSessionEnded("No refresh token.")
    try:
        response = requests.post(
            _endpoint("token_endpoint", "token/"),
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
            timeout=settings.PLATFORM_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PlatformUnavailable(str(exc)) from exc
    if response.status_code >= 500:
        raise PlatformUnavailable(f"HTTP {response.status_code}")
    if response.status_code != 200:
        # 400 invalid_grant / 401 invalid_client: izin dicabut, akun nonaktif, token dipakai ulang.
        raise PlatformSessionEnded(response.text[:200])
    save_token(request, response.json())
    return stored_token(request)


def access_token(request):
    """Access token yang masih berlaku (diperbarui dulu bila perlu)."""
    token = stored_token(request)
    if not token:
        raise PlatformSessionEnded("Not signed in with IoT Platform.")
    if is_expired(token):
        token = refresh(request)
    return token["access_token"]


def revoke(request):
    """Cabut refresh token di platform (saat logout). Gagal pun tidak apa-apa."""
    token = stored_token(request)
    if not token or not token.get("refresh_token"):
        return
    try:
        requests.post(
            _endpoint("revocation_endpoint", "revoke_token/"),
            data={
                "token": token["refresh_token"],
                "token_type_hint": "refresh_token",
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
            timeout=settings.PLATFORM_TIMEOUT,
        )
    except (requests.RequestException, PlatformUnavailable):
        pass


def api_get(request, path):
    """GET <PLATFORM_URL><path> dengan access token pengguna, mis. api_get(request, "/api/v2/me").

    401 dari API berarti token tidak berlaku lagi -> PlatformSessionEnded.
    """
    try:
        response = requests.get(
            f"{settings.PLATFORM_URL}{path}",
            headers={"Authorization": f"Bearer {access_token(request)}"},
            timeout=settings.PLATFORM_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PlatformUnavailable(str(exc)) from exc
    if response.status_code == 401:
        raise PlatformSessionEnded("The access token was refused.")
    if response.status_code >= 500:
        raise PlatformUnavailable(f"HTTP {response.status_code}")
    response.raise_for_status()
    return response.json()
