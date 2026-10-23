"""
Perintah kustom:  python manage.py runall

Menjalankan aplikasi MQTT Client dari SATU terminal (pengembangan):

    web    python manage.py runserver 127.0.0.1:9000   halaman web
    relay  python -m relay                             relay WebSocket -> TCP (mqtt://, mqtts://)

Keduanya tetap proses tersendiri (lihat launcher/supervisor.py): log digabung dengan awalan
nama, yang crash dinyalakan ulang otomatis, Ctrl+C mematikan semuanya.

    python manage.py runall                    # web di 127.0.0.1:9000 + relay
    python manage.py runall 127.0.0.1:9100     # web di port lain
    python manage.py runall --only web         # tanpa relay (hanya broker wss://)

Di server, keduanya dijalankan systemd: mqttc-web + mqttc-relay (docs/deploy.md).
"""
import hashlib
import importlib.util
import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from launcher.supervisor import Service, Supervisor

try:
    import fcntl  # macOS & Linux
except ImportError:  # Windows: tanpa kunci satu-instans
    fcntl = None

# nama layanan -> keterangan
SERVICES = {
    "web": "web pages",
    "relay": "WebSocket -> TCP relay for mqtt:// and mqtts://",
}
DEFAULT_ADDRPORT = "127.0.0.1:9000"


def parse_names(text):
    names = [n.strip() for n in (text or "").split(",") if n.strip()]
    unknown = [n for n in names if n not in SERVICES]
    if unknown:
        raise CommandError(f"Unknown service: {', '.join(unknown)}. Choose from: {', '.join(SERVICES)}.")
    return names


def split_addrport(addrport):
    if ":" in addrport:
        host, port = addrport.rsplit(":", 1)
    else:
        host, port = "127.0.0.1", addrport
    host = host.strip("[]") or "127.0.0.1"
    if not port.isdigit():
        raise CommandError(f"Invalid address:port {addrport!r}. Example: 127.0.0.1:9000")
    return host, int(port)


def port_in_use(host, port):
    """True bila port TCP sudah dipakai proses lain (mis. runserver yang masih jalan)."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return True
    return False


def installed(module):
    return importlib.util.find_spec(module) is not None


def relay_config():
    from relay.config import load_config

    return load_config()


class Command(BaseCommand):
    help = "Run the web server and the relay together (development)."

    def add_arguments(self, parser):
        parser.add_argument("addrport", nargs="?", default=DEFAULT_ADDRPORT,
                            help=f"Address for the web server (default {DEFAULT_ADDRPORT}).")
        parser.add_argument("--only", help="Comma-separated services to run: " + ", ".join(SERVICES))
        parser.add_argument("--skip", help="Comma-separated services to leave out.")
        parser.add_argument("--no-restart", action="store_true", help="Do not restart services that exit.")

    def warn(self, text):
        self.stdout.write(self.style.WARNING(f"[runall] {text}"))

    def handle(self, *args, **options):
        only, skip = parse_names(options["only"]), parse_names(options["skip"])
        names = [n for n in SERVICES if (not only or n in only) and n not in skip]
        names = self.preflight(names, options["addrport"], explicit=set(only))
        if not names:
            raise CommandError("Nothing to run.")

        lock = self.single_instance_lock()  # noqa: F841 (dipegang sampai proses selesai)

        base = str(settings.BASE_DIR)
        services = []
        for name in names:
            if name == "web":
                argv = [sys.executable, str(Path(base) / "manage.py"), "runserver", options["addrport"]]
            else:
                argv = [sys.executable, "-m", "relay"]
            services.append(Service(name=name, argv=argv))

        self.stdout.write(self.style.SUCCESS("[runall] Starting: " + ", ".join(
            f"{n} ({SERVICES[n]})" for n in names)))
        if "web" in names:
            host, port = split_addrport(options["addrport"])
            shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
            self.stdout.write(f"[runall] Open http://{shown}:{port}/ · Press Ctrl+C to stop everything.")
        # PYTHONPATH: "python -m relay" harus menemukan paket relay/ dari folder project,
        # dari mana pun runall dijalankan.
        pythonpath = os.pathsep.join(filter(None, [base, os.environ.get("PYTHONPATH", "")]))
        supervisor = Supervisor(services, out=self.stdout, restart=not options["no_restart"],
                                env={"PYTHONPATH": pythonpath})
        code = supervisor.run()
        if code:
            sys.exit(code)

    # --- pemeriksaan sebelum mulai -------------------------------------------------

    def preflight(self, names, addrport, explicit):
        """Buang layanan yang pasti gagal, dengan alasan yang jelas."""
        result = []
        for name in names:
            reason = None
            if name == "web":
                host, port = split_addrport(addrport)
                if port_in_use(host, port):
                    raise CommandError(
                        f"Port {port} is already in use. Is runserver (or another runall) still running?")
                if host in ("0.0.0.0", "::"):
                    self.warn("The web server is reachable from other computers on this network. "
                              "runserver is for development only.")
            elif name == "relay":
                reason = self.relay_problem(addrport)
            if reason:
                if name in explicit:
                    raise CommandError(f"Cannot run {name}: {reason}.")
                self.warn(f"Skipping {name}: {reason}.")
                continue
            result.append(name)
        return result

    def relay_problem(self, addrport):
        """Alasan relay tidak bisa jalan, atau None. Juga memperingatkan salah konfigurasi umum."""
        if not settings.RELAY_PUBLIC_URL:
            return "RELAY_PUBLIC_URL is empty in .env (mqtt:// and mqtts:// profiles are disabled)"
        if not installed("websockets"):
            return "websockets is not installed (pip install -r requirements.txt)"
        config = relay_config()
        if len(config.shared_secret) < 32:
            return "RELAY_SHARED_SECRET in .env must be 32+ random characters"
        if port_in_use(config.bind, config.port):
            return f"port {config.port} is already in use (is python -m relay still running?)"
        # Relay menukar tiket di web server INI. Port yang tidak cocok = setiap koneksi relay
        # gagal dengan "ticket expired".
        _, web_port = split_addrport(addrport)
        redeem_port = urlparse(config.redeem_url).port
        if redeem_port != web_port:
            self.warn(f"RELAY_REDEEM_URL points to port {redeem_port}, but the web server runs on {web_port}. "
                      f"Set RELAY_REDEEM_URL and RELAY_REPORT_URL in .env to http://127.0.0.1:{web_port}/internal/...")
        return None

    def single_instance_lock(self):
        """Cegah dua runall bersamaan (port web dan relay bentrok). Kunci dilepas otomatis."""
        if fcntl is None:
            return None
        digest = hashlib.sha1(str(settings.BASE_DIR).encode()).hexdigest()[:10]
        path = Path(tempfile.gettempdir()) / f"mqtt-client-runall-{digest}.lock"
        handle = open(path, "w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CommandError("runall is already running for this project (another terminal?).")
        return handle
