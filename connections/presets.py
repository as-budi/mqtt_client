"""
Templat profil siap pakai ("New connection" -> pilih templat).

Broker publik di bawah gratis dan TERBUKA: siapa saja bisa membaca topik Anda. Pakai
hanya untuk belajar, dengan nama topik yang unik.

Broker IoT Platform butuh login (username = password = access token device) dan setiap
device hanya boleh memakai topiknya sendiri. Cara termudah: Connections -> From IoT Platform,
yang membuat profil device lengkap dengan login dan topiknya.
"""
from urllib.parse import urlparse

from django.conf import settings

PUBLIC_PRESETS = {
    "emqx": {
        "label": "EMQX public broker",
        "data": {"name": "EMQX public", "scheme": "wss", "host": "broker.emqx.io", "port": 8084, "path": "/mqtt"},
    },
    "hivemq": {
        "label": "HiveMQ public broker",
        "data": {"name": "HiveMQ public", "scheme": "wss", "host": "broker.hivemq.com", "port": 8884, "path": "/mqtt"},
    },
    "mosquitto": {
        "label": "Eclipse Mosquitto test broker",
        "data": {"name": "Mosquitto test", "scheme": "wss", "host": "test.mosquitto.org", "port": 8081, "path": "/"},
    },
}


def platform_ws_url():
    """Alamat WebSocket broker IoT Platform, atau "" bila tidak diketahui."""
    if settings.PLATFORM_MQTT_WS_URL:
        return settings.PLATFORM_MQTT_WS_URL
    parsed = urlparse(settings.PLATFORM_URL)
    # Hanya platform https (server) yang punya wss://<domain>/mqtt (tahap 21 platform).
    # Platform di laptop (http://127.0.0.1:8000) biasanya memakai broker lain, mis. broker.emqx.io.
    return f"wss://{parsed.hostname}/mqtt" if parsed.scheme == "https" and parsed.hostname else ""


def platform_preset():
    """Broker IoT Platform lewat WebSocket, atau None bila alamatnya tidak diketahui."""
    url = urlparse(platform_ws_url())
    if url.scheme not in ("ws", "wss") or not url.hostname:
        return None
    return {
        "label": "IoT Platform broker (WebSocket)",
        "data": {"name": "IoT Platform", "scheme": url.scheme, "host": url.hostname,
                 "port": url.port or (443 if url.scheme == "wss" else 80), "path": url.path or "/mqtt",
                 "color": "green"},
    }


def all_presets():
    platform = platform_preset()
    return {**({"platform": platform} if platform else {}), **PUBLIC_PRESETS}
