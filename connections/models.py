"""
Profil koneksi broker MQTT dan langganan yang tersimpan (tahap M2).

Yang disimpan hanya PENGATURAN koneksi. Pesan MQTT tidak pernah disimpan di server
(hanya di memori browser, mulai tahap M3), dan password broker TIDAK punya kolom:
password ditanyakan saat Connect, atau diingat di browser bila pengguna memilih.

Dua jalur koneksi, ditentukan skema alamat (lihat docs/rencana-mqtt-client.md):

    wss:// ws://        Direct: browser langsung ke broker (MQTT over WebSocket)
    mqtts:// mqtt://    Relay:  browser -> relay di server -> TCP ke broker (tahap M4)
"""
from django.conf import settings
from django.db import models
from django.urls import reverse

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
    """Langganan yang dipasang otomatis setiap kali profil tersambung (tahap M3)."""

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
