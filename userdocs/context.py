"""
Fakta yang dipakai fragmen dokumentasi (tahap M13): alamat aplikasi dan IoT Platform, broker
platform, relay, dan batas-batas. Tidak bergantung pada pengguna, karena fragmen juga
dirender untuk indeks pencarian.
"""
import os

from django.conf import settings

from connections.presets import PUBLIC_PRESETS, platform_ws_url
from connections.saved import MAX_SAVED


def docs_context(request):
    base_url = request.build_absolute_uri("/").rstrip("/")
    ports = [p.strip() for p in os.getenv("RELAY_ALLOWED_PORTS", "1883,8883").split(",") if p.strip()]
    return {
        "app_url": base_url,
        "platform_url": settings.PLATFORM_URL,
        "platform_ws": platform_ws_url(),
        "relay": {
            "enabled": bool(settings.RELAY_PUBLIC_URL),
            "ports": ports,
            "per_user": int(os.getenv("RELAY_MAX_PER_USER", "5")),
            "idle_minutes": int(os.getenv("RELAY_IDLE_SECONDS", "600")) // 60,
            "max_hours": int(os.getenv("RELAY_MAX_SECONDS", str(12 * 3600))) // 3600,
            "rate_kb": int(os.getenv("RELAY_RATE_BYTES", str(64 * 1024))) // 1024,
        },
        "public_brokers": [preset["data"] for preset in PUBLIC_PRESETS.values()],
        "max_saved": MAX_SAVED,
        "snapshot": {"max_kb": settings.SNAPSHOT_PROXY_MAX_KB, "per_minute": settings.SNAPSHOT_PROXY_PER_MINUTE},
        "ui_style_selectable": settings.UI_STYLE_SELECTABLE,
        # Kunci indeks pencarian: alamat aplikasi ini (dipakai search.py).
        "http": {"base_url": base_url},
    }
