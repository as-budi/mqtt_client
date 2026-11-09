"""
Tahap M11: simulasi kamera ESP32-CAM. Unggahan snapshot dari halaman koneksi diteruskan ke
IoT Platform.

    POST /connections/<pk>/snapshot/      body = gambar (Content-Type: image/jpeg)
         header opsional: X-Command-Id, X-Source (command | periodic | device)

Mengapa lewat server ini, bukan langsung dari browser ke platform? Endpoint device platform
(POST /api/v1/<token>/snapshot, platform tahap 27a) berada di origin lain dan tidak membuka
CORS; membukanya juga melonggarkan endpoint yang dipakai perangkat sungguhan. Server ini
sudah bisa meminta token device ke API platform (seperti saat Connect), jadi cukup meneruskan.

Jawaban platform diteruskan apa adanya (201, 413, 415, 429, ...), supaya halaman bisa
menampilkan galat yang sama dengan yang diterima ESP32-CAM.
"""
import time

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import platform

from .session import error, own_profiles, platform_device

# Alamat unggah per (pengguna, profil) disimpan sebentar di cache server, supaya snapshot
# berkala tidak memanggil API platform setiap kali. Alamatnya memuat token device.
TARGET_SECONDS = 300
SOURCES = {"command", "periodic", "device"}


def _target_key(request, profile):
    return f"mqttc:snapshot-url:{request.user.pk}:{profile.pk}"


def snapshot_target(request, profile, refresh=False):
    """URL unggah snapshot device profil ini (dari /api/v2/me/devices). Bisa melempar error platform."""
    key = _target_key(request, profile)
    url = None if refresh else cache.get(key)
    if url:
        return url
    device, _broker = platform_device(request, profile.platform_device_id)
    if device is None:
        raise LookupError("This device no longer exists on IoT Platform, or it is not shared with you anymore.")
    token = device.get("access_token")
    if not token:
        raise PermissionError("You need Editor access to this device on IoT Platform to upload as the device.")
    # Platform lama tanpa "snapshot_url": susun sendiri (jalurnya sama dengan platform tahap 27a).
    url = device.get("snapshot_url") or f"{settings.PLATFORM_URL}/api/v1/{token}/snapshot"
    cache.set(key, url, TARGET_SECONDS)
    return url


def too_many(request):
    """Batas laju per pengguna (selain batas di platform): SNAPSHOT_PROXY_PER_MINUTE."""
    limit = settings.SNAPSHOT_PROXY_PER_MINUTE
    if not limit:
        return False
    key = f"mqttc:snapshot-rate:{request.user.pk}:{int(time.time() // 60)}"
    cache.add(key, 0, 90)
    try:
        count = cache.incr(key)
    except ValueError:          # kunci hilang (cache dibersihkan): mulai lagi
        cache.set(key, 1, 90)
        count = 1
    return count > limit


@login_required
@require_POST
def upload(request, pk):
    profile = get_object_or_404(own_profiles(request), pk=pk)
    if profile.platform_device_id is None:
        return error(400, "Camera simulation needs a connection made from an IoT Platform device.")
    max_bytes = settings.SNAPSHOT_PROXY_MAX_KB * 1024
    length = request.META.get("CONTENT_LENGTH") or "0"
    if length.isdigit() and int(length) > max_bytes:
        return error(413, f"The image is larger than {settings.SNAPSHOT_PROXY_MAX_KB} KB (this app's limit).")
    body = request.body
    if not body:
        return error(400, "The request body is empty.")
    content_type = (request.content_type or "").lower()
    if not content_type.startswith("image/"):
        return error(415, "Send the image as the body with an image/* Content-Type.")
    if too_many(request):
        return error(429, f"At most {settings.SNAPSHOT_PROXY_PER_MINUTE} images a minute from this app.")

    headers = {"Content-Type": content_type}
    command_id = request.headers.get("X-Command-Id", "").strip()
    if command_id.isdigit():
        headers["X-Command-Id"] = command_id
    source = request.headers.get("X-Source", "").strip().lower()
    if source in SOURCES:
        headers["X-Source"] = source

    try:
        url = snapshot_target(request, profile)
    except platform.PlatformSessionEnded:
        return error(401, "Your IoT Platform session has ended. Sign in again.", signin=reverse("accounts:login"))
    except platform.PlatformUnavailable:
        return error(503, "IoT Platform cannot be reached right now.")
    except platform.PlatformForbidden:
        return error(403, "Sign out and sign in again to allow this app to read your devices.")
    except (LookupError, PermissionError) as exc:
        return error(403, str(exc))

    try:
        response = requests.post(url, data=body, headers=headers, timeout=settings.PLATFORM_TIMEOUT)
    except requests.RequestException:
        return error(503, "IoT Platform cannot be reached right now; the image was not uploaded.")
    if response.status_code == 401:
        # Token device diganti (Regenerate token) sejak alamatnya disimpan: lupakan alamat lama.
        cache.delete(_target_key(request, profile))
    try:
        data = response.json()
    except ValueError:
        data = {"error": f"IoT Platform answered HTTP {response.status_code}."}
    if not isinstance(data, dict):
        data = {"result": data}
    return JsonResponse(data, status=response.status_code)
