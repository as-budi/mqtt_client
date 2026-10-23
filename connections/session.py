"""
Halaman koneksi (tahap M3): tempat Connect, subscribe, melihat pesan, dan publish.

    GET  /connections/<pk>/           halaman koneksi (JavaScript: static/js/session.js)
    POST /connections/<pk>/connect/   bahan untuk satu kali connect (JSON), lihat connect_info()

Protokol MQTT dijalankan pustaka mqtt.js DI BROWSER. Server hanya menyiapkan:

    - alamat yang dibuka browser: alamat broker (jalur Direct, wss://) atau alamat relay
      bertiket (jalur Relay, mqtt:// dan mqtts://, tahap M4);
    - client ID acak, pengaturan sesi, dan Last Will;
    - untuk profil dari device IoT Platform: access token device (diambil dari API
      platform SAAT ITU, tidak disimpan), dan topik dengan {token}/{prefix} yang sudah diisi.

Password broker biasa TIDAK pernah lewat server: diketik di browser dan langsung
dipakai mqtt.js.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts import platform

from .models import ConnectionProfile, RelayTicket


def own_profiles(request):
    return ConnectionProfile.objects.filter(owner=request.user)


def error(status, message, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


def fill(text, values):
    """Isi {token} dan {prefix} pada topik profil dari device platform."""
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def platform_device(request, device_id):
    """Data satu device dari /api/v2/me/devices (atau None), beserta info broker."""
    data = platform.api_get(request, "/api/v2/me/devices")
    for device in data.get("devices", []):
        if device["id"] == device_id:
            return device, data["broker"]
    return None, data.get("broker", {})


@login_required
def session_page(request, pk):
    profile = get_object_or_404(own_profiles(request).prefetch_related("subscriptions"), pk=pk)
    config = {
        "id": profile.pk,
        "name": profile.name,
        "url": profile.url,
        "route": profile.route,
        "username": profile.username,
        "platformDevice": profile.platform_device_id is not None,
        "protocolVersion": profile.protocol_version,
        "subscriptions": [
            {"topic": s.topic_filter, "qos": s.qos, "color": s.color, "muted": s.muted}
            for s in profile.subscriptions.all()
        ],
        "urls": {
            "connect": reverse("connections:connect", args=[profile.pk]),
            "saved": reverse("connections:saved", args=[profile.pk]),
            "savedDelete": reverse("connections:saved_delete", args=[0]),
            "relayStatus": reverse("connections:relay_status", args=[0]),
            "edit": reverse("connections:edit", args=[profile.pk]),
        },
    }
    return render(request, "connections/session.html", {"profile": profile, "config": config})


@login_required
@require_POST
def connect_info(request, pk):
    """Bahan untuk SATU kali connect. Dipanggil lagi setiap reconnect (tiket relay sekali pakai)."""
    profile = get_object_or_404(own_profiles(request).prefetch_related("subscriptions"), pk=pk)
    values, username, password, topics, device_info, sandbox_info = {}, profile.username, None, None, None, None

    if profile.platform_sandbox:
        # Akun MQTT sandbox pengguna di broker platform (tahap M5; platform tahap 23).
        try:
            sandbox = platform.api_get(request, "/api/v2/me/sandbox")
        except platform.PlatformSessionEnded:
            return error(401, "Your IoT Platform session has ended. Sign in again.",
                         signin=reverse("accounts:login"))
        except platform.PlatformUnavailable:
            return error(503, "IoT Platform cannot be reached right now, so the sandbox password is unavailable.")
        except platform.PlatformForbidden:
            return error(403, "Sign out and sign in again to allow this app to use your MQTT sandbox account.")
        if not sandbox.get("enabled"):
            return error(403, "You have no MQTT sandbox account. Create it in your IoT Platform profile.",
                         manage=sandbox.get("manage_url"))
        username, password = sandbox["username"], sandbox["password"]
        values = {"sandbox": sandbox["topic_root"]}
        sandbox_info = {"root": sandbox["topic_root"], "shared": sandbox["shared_root"]}

    if profile.platform_device_id is not None:
        try:
            device, broker = platform_device(request, profile.platform_device_id)
        except platform.PlatformSessionEnded:
            return error(401, "Your IoT Platform session has ended. Sign in again.",
                         signin=reverse("accounts:login"))
        except platform.PlatformUnavailable:
            return error(503, "IoT Platform cannot be reached right now, so the device token is unavailable.")
        if device is None:
            return error(403, "This device no longer exists on IoT Platform, or it is not shared with you anymore.")
        if not device.get("access_token"):
            return error(403, "You need Editor access to this device on IoT Platform to connect as the device.")
        token = device["access_token"]
        values = {"token": token, "prefix": broker.get("topic_prefix", "")}
        username = password = token
        topics = device.get("topics")
        # Untuk simulator, auto-responder, dan simulasi OTA di halaman koneksi (tahap M5).
        device_info = {"name": device["name"], "board": device.get("board") or "sim",
                       "firmware": device.get("firmware_version") or "1.0.0",
                       "variables": device.get("variables", [])}

    data = {
        "route": profile.route,
        "clientId": f"{profile.client_id_prefix}{secrets.token_hex(4)}",
        "username": username or None,
        "password": password,                 # hanya untuk device platform; selain itu diketik pengguna
        "askPassword": bool(username) and password is None,
        "options": {
            "protocolVersion": profile.protocol_version,
            "keepalive": profile.keepalive,
            "clean": profile.clean_start,
        },
        "subscriptions": [
            {"topic": fill(s.topic_filter, values), "qos": s.qos, "color": s.color, "muted": s.muted}
            for s in profile.subscriptions.all()
        ],
        "topics": topics,
        "device": device_info,
        "sandbox": sandbox_info,
    }
    if profile.will_topic:
        data["options"]["will"] = {
            "topic": fill(profile.will_topic, values), "payload": fill(profile.will_payload, values),
            "qos": profile.will_qos, "retain": profile.will_retain,
        }

    if profile.route == "direct":
        data["url"] = profile.url
        return JsonResponse(data)

    # Jalur Relay (tahap M4): browser membuka relay di server ini dengan tiket sekali pakai.
    if not settings.RELAY_PUBLIC_URL:
        return error(503, "This server has no relay for mqtt:// and mqtts:// brokers. "
                          "Use a broker with a WebSocket port (wss://).")
    now = timezone.now()
    recent = RelayTicket.objects.filter(user=request.user, created_at__gte=now - timedelta(minutes=1)).count()
    if recent >= settings.RELAY_TICKETS_PER_MINUTE:
        return error(429, "Too many connection attempts. Wait a minute and try again.")
    # Bersihkan tiket lama sambil lalu (cukup murah: kolom created_at diindeks).
    RelayTicket.objects.filter(created_at__lt=now - timedelta(hours=1)).delete()
    ticket, token = RelayTicket.issue(request.user, profile)
    data["url"] = settings.RELAY_PUBLIC_URL + token
    data["ticketId"] = ticket.pk
    return JsonResponse(data)
