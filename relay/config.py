"""
Pengaturan relay, dibaca dari environment / file .env yang SAMA dengan Django.

    RELAY_BIND, RELAY_PORT          alamat dengar (bawaan 127.0.0.1:8003, di belakang Nginx)
    RELAY_REDEEM_URL                endpoint Django untuk menukar tiket
    RELAY_REPORT_URL                endpoint Django untuk melaporkan kegagalan
    RELAY_SHARED_SECRET             rahasia bersama dengan Django (wajib)
    RELAY_ALLOWED_PORTS             port broker yang boleh dituju, bawaan "1883,8883"
    RELAY_DENY_HOSTS                host yang diblokir (dipisah koma; juga subdomainnya)
    RELAY_ALLOW_LOCAL               True = boleh ke localhost/LAN. HANYA untuk laptop, JANGAN di server
    RELAY_ORIGINS                   halaman yang boleh membuka relay, mis. https://mqtt.domain (kosong = semua)
    RELAY_MAX_PER_USER, RELAY_MAX_TOTAL, RELAY_RATE_BYTES, RELAY_MAX_FRAME,
    RELAY_IDLE_SECONDS, RELAY_MAX_SECONDS, RELAY_CONNECT_TIMEOUT
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _list(value):
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    bind: str = "127.0.0.1"
    port: int = 8003
    path_prefix: str = "/relay/"
    redeem_url: str = "http://127.0.0.1:8002/internal/relay/redeem/"
    report_url: str = "http://127.0.0.1:8002/internal/relay/report/"
    shared_secret: str = ""
    allowed_ports: set = field(default_factory=lambda: {1883, 8883})
    deny_hosts: list = field(default_factory=list)
    allow_local: bool = False
    origins: list = field(default_factory=list)
    max_per_user: int = 5
    max_total: int = 200
    rate_bytes: int = 64 * 1024         # per detik, per arah, per koneksi
    max_frame: int = 256 * 1024
    idle_seconds: int = 600
    max_seconds: int = 12 * 3600
    connect_timeout: float = 10
    first_frame_timeout: float = 10


def load_config():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    env = os.getenv
    return Config(
        bind=env("RELAY_BIND", "127.0.0.1"),
        port=int(env("RELAY_PORT", "8003")),
        redeem_url=env("RELAY_REDEEM_URL", "http://127.0.0.1:8002/internal/relay/redeem/"),
        report_url=env("RELAY_REPORT_URL", "http://127.0.0.1:8002/internal/relay/report/"),
        shared_secret=env("RELAY_SHARED_SECRET", ""),
        allowed_ports={int(p) for p in _list(env("RELAY_ALLOWED_PORTS", "1883,8883"))},
        deny_hosts=[h.lower().rstrip(".") for h in _list(env("RELAY_DENY_HOSTS", ""))],
        allow_local=env("RELAY_ALLOW_LOCAL", "False") == "True",
        origins=_list(env("RELAY_ORIGINS", "")),
        max_per_user=int(env("RELAY_MAX_PER_USER", "5")),
        max_total=int(env("RELAY_MAX_TOTAL", "200")),
        rate_bytes=int(env("RELAY_RATE_BYTES", str(64 * 1024))),
        max_frame=int(env("RELAY_MAX_FRAME", str(256 * 1024))),
        idle_seconds=int(env("RELAY_IDLE_SECONDS", "600")),
        max_seconds=int(env("RELAY_MAX_SECONDS", str(12 * 3600))),
        connect_timeout=float(env("RELAY_CONNECT_TIMEOUT", "10")),
    )
