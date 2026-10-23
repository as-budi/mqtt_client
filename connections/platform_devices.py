"""
Profil koneksi dari device IoT Platform (tahap M3).

    GET  /connections/platform/              device milik pengguna + yang dibagikan (API platform)
    POST /connections/platform/<device_id>/  buat profil untuk device itu (atau buka yang sudah ada)
    POST /connections/platform/sandbox/      profil akun MQTT sandbox pengguna (tahap M5)

Profil seperti ini login SEBAGAI device: username = password = access token device.
Token TIDAK disimpan di sini. Profil hanya mengingat id device; token dan topik diambil
lagi dari API platform setiap kali Connect (connections/session.py). Bila token
di-*regenerate* di platform, profil tetap jalan.

Topik langganan ditulis dengan {prefix} dan {token}, mis. "{prefix}/{token}/desired",
dan diisi saat Connect. Hanya topik yang diizinkan ACL broker platform untuk device:
desired, commands/+, errors (baca) serta telemetry, commands/<id>/response, firmware,
status (tulis).
"""
from urllib.parse import urlparse

import requests

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts import platform

from .models import Color, ConnectionProfile, Qos, Scheme, SubscriptionPreset

DEVICE_SUBSCRIPTIONS = [
    ("{prefix}/{token}/desired", Qos.AT_LEAST_ONCE, Color.GREEN),
    ("{prefix}/{token}/commands/+", Qos.AT_LEAST_ONCE, Color.ORANGE),
    ("{prefix}/{token}/errors", Qos.AT_MOST_ONCE, Color.RED),
]


def broker_address(broker):
    """Alamat broker untuk profil: WebSocket (Direct) bila ada, kalau tidak TCP (Relay)."""
    websocket = broker.get("websocket")
    if websocket:
        parsed = urlparse(websocket)
        scheme = Scheme.WSS if parsed.scheme == "wss" else Scheme.WS
        return {"scheme": scheme, "host": parsed.hostname, "port": parsed.port, "path": parsed.path or "/"}
    mqtt = broker.get("mqtt", {})
    return {"scheme": Scheme.MQTTS if mqtt.get("tls") else Scheme.MQTT,
            "host": mqtt.get("host", ""), "port": mqtt.get("port"), "path": ""}


def _load(request):
    """Data dari API platform, atau (None, response-redirect) bila gagal."""
    try:
        return platform.api_get(request, "/api/v2/me/devices"), None
    except platform.PlatformSessionEnded:
        logout(request)
        messages.info(request, "Your IoT Platform session has ended. Please sign in again.")
        return None, redirect("accounts:welcome")
    except platform.PlatformUnavailable:
        messages.error(request, "IoT Platform cannot be reached right now. Try again in a moment.")
        return None, redirect("connections:list")


@login_required
def device_list(request):
    if not request.user.platform_sub:
        messages.info(request, "Only accounts from IoT Platform can list platform devices.")
        return redirect("connections:list")
    data, response = _load(request)
    if response:
        return response
    existing = dict(ConnectionProfile.objects.filter(owner=request.user, platform_device_id__isnull=False)
                    .values_list("platform_device_id", "pk"))
    devices = [{**device, "profile_id": existing.get(device["id"])} for device in data["devices"]]
    sandbox = load_sandbox(request)
    sandbox_profile = ConnectionProfile.objects.filter(owner=request.user, platform_sandbox=True).first()
    return render(request, "connections/platform_devices.html", {
        "devices": devices, "broker": data["broker"], "sandbox": sandbox, "sandbox_profile": sandbox_profile,
    })


def load_sandbox(request):
    """Info akun sandbox dari platform, atau None bila tidak tersedia / belum diizinkan."""
    try:
        return platform.api_get(request, "/api/v2/me/sandbox")
    except platform.PlatformForbidden:
        return {"available": True, "enabled": False, "needs_consent": True}
    except (platform.PlatformUnavailable, platform.PlatformSessionEnded, requests.RequestException):
        return None


@login_required
@require_POST
def sandbox_create(request):
    existing = ConnectionProfile.objects.filter(owner=request.user, platform_sandbox=True).first()
    if existing:
        return redirect("connections:session", pk=existing.pk)
    sandbox = load_sandbox(request)
    if not sandbox or not sandbox.get("enabled"):
        messages.error(request, "Create your MQTT sandbox account in your IoT Platform profile first.")
        return redirect("connections:platform")
    with transaction.atomic():
        profile = ConnectionProfile.objects.create(
            owner=request.user,
            name=_unique_name(request.user, "IoT Platform sandbox"),
            color=Color.PURPLE,
            platform_sandbox=True,
            client_id_prefix="mqttc-sbx-",
            position=ConnectionProfile.objects.filter(owner=request.user).count(),
            **broker_address(sandbox["broker"]),
        )
        SubscriptionPreset.objects.create(profile=profile, topic_filter="{sandbox}/#", qos=Qos.AT_MOST_ONCE,
                                          color=Color.PURPLE, position=0)
    messages.success(request, "Created a connection for your MQTT sandbox account.")
    return redirect("connections:session", pk=profile.pk)


def _unique_name(owner, name):
    names = {n.lower() for n in ConnectionProfile.objects.filter(owner=owner).values_list("name", flat=True)}
    candidate, number = name[:80], 2
    while candidate.lower() in names:
        candidate = f"{name[:70]} ({number})"
        number += 1
    return candidate


@login_required
@require_POST
def device_create(request, device_id):
    existing = ConnectionProfile.objects.filter(owner=request.user, platform_device_id=device_id).first()
    if existing:
        return redirect("connections:session", pk=existing.pk)
    data, response = _load(request)
    if response:
        return response
    device = next((d for d in data["devices"] if d["id"] == device_id), None)
    if device is None or not device.get("access_token"):
        messages.error(request, "You need Editor access to this device on IoT Platform to connect as the device.")
        return redirect("connections:platform")
    with transaction.atomic():
        profile = ConnectionProfile.objects.create(
            owner=request.user,
            name=_unique_name(request.user, device["name"]),
            color=Color.GREEN,
            platform_device_id=device_id,
            client_id_prefix="mqttc-dev-",
            position=ConnectionProfile.objects.filter(owner=request.user).count(),
            **broker_address(data["broker"]),
        )
        for position, (topic, qos, color) in enumerate(DEVICE_SUBSCRIPTIONS):
            SubscriptionPreset.objects.create(profile=profile, topic_filter=topic, qos=qos, color=color,
                                              position=position)
    messages.success(request, f"Created a connection for device \"{device['name']}\".")
    return redirect("connections:session", pk=profile.pk)
