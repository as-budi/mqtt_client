"""Form profil koneksi dan formset langganan tersimpan."""
import re
import ssl

from django import forms
from django.conf import settings
from django.forms import inlineformset_factory

from .models import ConnectionProfile, Scheme, SubscriptionPreset

# Nama host: huruf, angka, titik, tanda hubung (termasuk alamat IPv4); IPv6 dalam [ ].
HOST_RE = re.compile(r"^(\[[0-9a-fA-F:.]+\]|[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")


class BootstrapMixin:
    """Beri kelas CSS Bootstrap ke setiap widget."""

    def style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class ConnectionProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ConnectionProfile
        fields = [
            "name", "color", "scheme", "host", "port", "path",
            "client_id_prefix", "username", "protocol_version", "keepalive", "clean_start",
            "will_topic", "will_payload", "will_qos", "will_retain", "ca_pem",
        ]
        widgets = {"will_payload": forms.Textarea(attrs={"rows": 2}),
                   "ca_pem": forms.Textarea(attrs={"rows": 4, "class": "form-control font-monospace small",
                                                   "placeholder": "-----BEGIN CERTIFICATE-----"})}

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.style_fields()
        self.fields["port"].widget.attrs.update(min=1, max=65535)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        taken = ConnectionProfile.objects.filter(owner=self.owner, name__iexact=name).exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("You already have a connection with this name.")
        return name

    def clean_host(self):
        host = self.cleaned_data["host"].strip()
        if "://" in host or "/" in host:
            raise forms.ValidationError("Enter only the host name, without wss:// or a path. "
                                        "Choose the protocol and path in their own fields.")
        if not HOST_RE.match(host):
            raise forms.ValidationError("This is not a valid host name or IP address.")
        return host.lower()

    def clean_port(self):
        port = self.cleaned_data["port"]
        if port is not None and not 1 <= port <= 65535:
            raise forms.ValidationError("A port is a number from 1 to 65535.")
        return port

    def clean_keepalive(self):
        keepalive = self.cleaned_data["keepalive"]
        if keepalive > 65535:
            raise forms.ValidationError("Keep alive can be at most 65535 seconds.")
        return keepalive

    def clean_ca_pem(self):
        """Harus sertifikat PEM yang bisa dibaca modul ssl (bukan kunci privat)."""
        pem = self.cleaned_data["ca_pem"].strip()
        if not pem:
            return ""
        if "PRIVATE KEY" in pem:
            raise forms.ValidationError("This is a private key. Paste only the CA certificate (public).")
        try:
            ssl.create_default_context().load_verify_locations(cadata=pem)
        except (ssl.SSLError, ValueError):
            raise forms.ValidationError("This is not a valid PEM certificate (-----BEGIN CERTIFICATE----- ...).")
        return pem + "\n"

    def clean(self):
        data = super().clean()
        scheme = data.get("scheme")
        if scheme != Scheme.MQTTS:
            data["ca_pem"] = ""
        if scheme in (Scheme.WSS, Scheme.WS):
            path = (data.get("path") or "").strip() or "/"
            if not path.startswith("/"):
                path = "/" + path
            data["path"] = path
            # Halaman https:// tidak boleh membuka ws:// (aturan "mixed content" browser).
            if scheme == Scheme.WS and not settings.DEBUG:
                self.add_error("scheme", "Browsers block ws:// on a secure (https) page. Use wss://, "
                                         "or mqtt:// through the relay.")
        else:
            data["path"] = ""
        if data.get("will_payload") and not data.get("will_topic"):
            self.add_error("will_topic", "Enter the topic for the Last Will payload.")
        return data


class SubscriptionPresetForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SubscriptionPreset
        fields = ["topic_filter", "qos", "color", "muted"]
        widgets = {"topic_filter": forms.TextInput(attrs={"placeholder": "e.g. iot/+/telemetry"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


# Topic filter ganda dalam satu profil ditolak otomatis oleh formset Django (validate_unique),
# karena model punya UniqueConstraint(profile, topic_filter).
SubscriptionFormSet = inlineformset_factory(
    ConnectionProfile, SubscriptionPreset, form=SubscriptionPresetForm,
    extra=1, can_delete=True, max_num=50, validate_max=True,
)
