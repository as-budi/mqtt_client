"""
Templat profil siap pakai ("New connection" -> pilih templat).

Broker publik di bawah gratis dan TERBUKA: siapa saja bisa membaca topik Anda. Pakai
hanya untuk belajar, dengan nama topik yang unik.

Broker IoT Platform butuh login (username = password = access token device) dan setiap
device hanya boleh memakai topiknya sendiri. Mulai tahap M3, profil untuk device
platform bisa dibuat langsung dari daftar device.
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


def platform_preset():
    """Broker IoT Platform lewat WebSocket, dari alamat platform (PLATFORM_URL)."""
    host = urlparse(settings.PLATFORM_URL).hostname or "localhost"
    return {
        "label": "IoT Platform broker (WebSocket)",
        "data": {"name": "IoT Platform", "scheme": "wss", "host": host, "port": 443, "path": "/mqtt", "color": "green"},
    }


def all_presets():
    return {"platform": platform_preset(), **PUBLIC_PRESETS}
