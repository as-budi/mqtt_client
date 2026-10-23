"""
Profil koneksi broker MQTT dan langganan yang tersimpan (tahap M2).

Yang disimpan hanya PENGATURAN koneksi. Pesan MQTT tidak pernah disimpan di server
(hanya di memori browser, mulai tahap M3), dan password broker TIDAK punya kolom:
password ditanyakan saat Connect, atau diingat di browser bila pengguna memilih.

Dua jalur koneksi, ditentukan skema alamat (lihat docs/rencana-mqtt-client.md):

    wss:// ws://        Direct: browser langsung ke broker (MQTT over WebSocket)
    mqtts:// mqtt://    Relay:  browser -> relay di server -> TCP ke broker (tahap M4)
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .validators import validate_topic_filter, validate_topic_name


class Scheme(models.TextChoices):
    WSS = "wss", "wss:// (WebSocket over TLS)"
    WS = "ws", "ws:// (WebSocket, no encryption)"
    MQTTS = "mqtts", "mqtts:// (TCP over TLS, via relay)"
    MQTT = "mqtt", "mqtt:// (TCP, no encryption, via relay)"


DEFAULT_PORTS = {Scheme.WSS: 443, Scheme.WS: 80, Scheme.MQTTS: 8883, Scheme.MQTT: 1883}
WEBSOCKET_SCHEMES = {Scheme.WSS, Scheme.WS}
TLS_SCHEMES = {Scheme.WSS, Scheme.MQTTS}


class Qos(models.IntegerChoices):
    AT_MOST_ONCE = 0, "0 (at most once)"
    AT_LEAST_ONCE = 1, "1 (at least once)"
    EXACTLY_ONCE = 2, "2 (exactly once)"


class ProtocolVersion(models.IntegerChoices):
    # Angka ini yang dikirim di paket CONNECT (protocol level).
    V311 = 4, "MQTT 3.1.1"
    V5 = 5, "MQTT 5.0"


class Color(models.TextChoices):
    BLUE = "blue", "Blue"
    GREEN = "green", "Green"
    ORANGE = "orange", "Orange"
    PURPLE = "purple", "Purple"
    RED = "red", "Red"
    GRAY = "gray", "Gray"


class ConnectionProfile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connections")
    name = models.CharField("name", max_length=80)
    color = models.CharField("color", max_length=10, choices=Color.choices, default=Color.BLUE)

    # --- Broker ---
    scheme = models.CharField("protocol", max_length=5, choices=Scheme.choices, default=Scheme.WSS)
    host = models.CharField("host", max_length=253, help_text="Name or IP address only, e.g. broker.emqx.io")
    port = models.PositiveIntegerField("port", null=True, blank=True,
                                       help_text="Empty = default for the protocol (wss 443, mqtts 8883, ...).")
    path = models.CharField("WebSocket path", max_length=200, blank=True, default="/mqtt",
                            help_text="Only for ws:// and wss://, usually /mqtt.")

    # --- Login dan sesi ---
    client_id_prefix = models.CharField(
        "client ID prefix", max_length=40, blank=True, default="mqttc-",
        help_text="A random part is added on each connect, so two tabs never kick each other out.",
    )
    username = models.CharField("username", max_length=200, blank=True)
    protocol_version = models.PositiveSmallIntegerField(
        "MQTT version", choices=ProtocolVersion.choices, default=ProtocolVersion.V311)
    keepalive = models.PositiveIntegerField("keep alive (s)", default=60)
    clean_start = models.BooleanField("clean start", default=True,
                                      help_text="Start a new session; the broker forgets old subscriptions.")

    # --- Last Will ---
    will_topic = models.CharField("Last Will topic", max_length=500, blank=True,
                                  validators=[validate_topic_name],
                                  help_text="Published by the broker if this connection drops without a goodbye.")
    will_payload = models.TextField("Last Will payload", blank=True)
    will_qos = models.PositiveSmallIntegerField("Last Will QoS", choices=Qos.choices, default=Qos.AT_MOST_ONCE)
    will_retain = models.BooleanField("Last Will retained", default=False)

    # Profil yang dibuat dari device IoT Platform (tahap M3): token diambil ulang dari API.
    platform_device_id = models.PositiveIntegerField("IoT Platform device", null=True, blank=True)
    # Profil akun MQTT sandbox pengguna di broker platform (tahap M5): username/password
    # diambil dari API platform saat Connect; topik boleh memakai {sandbox} = sandbox/<username>.
    platform_sandbox = models.BooleanField("IoT Platform sandbox", default=False)

    # CA sendiri untuk mqtts:// lewat relay (tahap M6), mis. broker lab bersertifikat self-signed.
    # Sertifikat PUBLIK (PEM), bukan rahasia. Kosong = hanya CA umum (daftar CA sistem).
    ca_pem = models.TextField("custom CA certificate (PEM)", blank=True, max_length=20000,
                              help_text="Only for mqtts://. Paste the broker's CA certificate if it is self-signed.")

    position = models.PositiveIntegerField("order", default=0)
    created_at = models.DateTimeField("created", auto_now_add=True)
    updated_at = models.DateTimeField("updated", auto_now=True)

    class Meta:
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="connection_unique_name_per_owner"),
        ]

    def __str__(self):
        return self.name

    @property
    def from_platform(self):
        return self.platform_device_id is not None or self.platform_sandbox

    def get_absolute_url(self):
        return reverse("connections:edit", args=[self.pk])

    @property
    def effective_port(self):
        return self.port or DEFAULT_PORTS[self.scheme]

    @property
    def is_websocket(self):
        return self.scheme in WEBSOCKET_SCHEMES

    @property
    def uses_tls(self):
        return self.scheme in TLS_SCHEMES

    @property
    def route(self):
        """"direct" (browser ke broker) atau "relay" (lewat server, tahap M4)."""
        return "direct" if self.is_websocket else "relay"

    @property
    def url(self):
        """Alamat lengkap, mis. wss://broker.emqx.io:8084/mqtt atau mqtts://iot.domain:8883."""
        address = f"{self.scheme}://{self.host}:{self.effective_port}"
        return address + (self.path or "/") if self.is_websocket else address


class SubscriptionPreset(models.Model):
    """Langganan yang dipasang otomatis setiap kali profil tersambung (tahap M3).

    Untuk profil dari device IoT Platform, topik boleh memuat {token} dan {prefix}, mis.
    "{prefix}/{token}/desired". Keduanya diisi saat Connect dari API platform, sehingga
    access token device tidak pernah tersimpan di database aplikasi ini.
    """

    profile = models.ForeignKey(ConnectionProfile, on_delete=models.CASCADE, related_name="subscriptions")
    topic_filter = models.CharField("topic filter", max_length=500, validators=[validate_topic_filter])
    qos = models.PositiveSmallIntegerField("QoS", choices=Qos.choices, default=Qos.AT_MOST_ONCE)
    color = models.CharField("color", max_length=10, choices=Color.choices, default=Color.GRAY)
    muted = models.BooleanField("muted", default=False, help_text="Subscribed, but messages are hidden.")
    position = models.PositiveIntegerField("order", default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "topic_filter"], name="subscription_unique_per_profile"),
        ]

    def __str__(self):
        return self.topic_filter


class SavedMessage(models.Model):
    """Pesan publish yang disimpan untuk dipakai lagi ("Saved messages", tahap M3)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_messages")
    # Kosong = tersedia di semua koneksi milik pengguna ini.
    profile = models.ForeignKey(ConnectionProfile, null=True, blank=True, on_delete=models.CASCADE,
                                related_name="saved_messages")
    name = models.CharField("name", max_length=80)
    topic = models.CharField("topic", max_length=500, validators=[validate_topic_name])
    payload = models.TextField("payload", blank=True, max_length=65536)
    qos = models.PositiveSmallIntegerField("QoS", choices=Qos.choices, default=Qos.AT_MOST_ONCE)
    retain = models.BooleanField("retain", default=False)
    created_at = models.DateTimeField("created", auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    def as_dict(self):
        return {"id": self.pk, "name": self.name, "topic": self.topic, "payload": self.payload,
                "qos": self.qos, "retain": self.retain, "profile": self.profile_id}


class RelayTicket(models.Model):
    """Tiket sekali pakai untuk relay WebSocket -> TCP (tahap M4).

    Browser tidak pernah memberi tahu relay ke mana harus menyambung. Django memeriksa
    pengguna dan profil, lalu menyimpan tujuan (host, port, TLS) di tiket ini. Relay
    menukarkan tiket lewat endpoint internal (connections/relay.py) dan baru tahu
    tujuannya saat itu. Tiket berlaku RELAY_TICKET_SECONDS (60 detik) dan sekali pakai.

    Yang disimpan hanya HASH tiket (seperti password): kebocoran database tidak
    membuat tiket yang masih berlaku bisa dipakai.
    """

    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="relay_tickets")
    profile = models.ForeignKey(ConnectionProfile, null=True, on_delete=models.SET_NULL, related_name="+")
    host = models.CharField(max_length=253)
    port = models.PositiveIntegerField()
    tls = models.BooleanField()
    ca_pem = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    # Diisi relay bila koneksi gagal, mis. "address_not_allowed", untuk pesan di browser.
    failure = models.CharField(max_length=40, blank=True)
    failure_detail = models.CharField(max_length=200, blank=True)

    @staticmethod
    def hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def issue(cls, user, profile):
        """Buat tiket baru; mengembalikan (tiket, token-teks-asli)."""
        token = secrets.token_urlsafe(32)
        ticket = cls.objects.create(token_hash=cls.hash(token), user=user, profile=profile,
                                    host=profile.host, port=profile.effective_port, tls=profile.uses_tls,
                                    ca_pem=profile.ca_pem if profile.uses_tls else "")
        return ticket, token
