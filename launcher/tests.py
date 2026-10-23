"""Tes runall: supervisor dengan proses Python kecil sebagai pengganti layanan, dan pemeriksaan awal."""
import io
import os
import re
import socket
import sys
import time
import unittest
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from launcher.management.commands import runall
from launcher.supervisor import Service, Supervisor
from relay.config import Config


def alive(pid):
    """True bila proses masih berjalan (zombie = sudah mati, tinggal menunggu dibereskan)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().split(")")[-1].split()[0] != "Z"
    except FileNotFoundError:
        return True


def python(code):
    return [sys.executable, "-c", code]


class SupervisorTests(SimpleTestCase):
    def test_output_is_prefixed_and_crashes_are_restarted_then_given_up(self):
        out = io.StringIO()
        service = Service("crashy", python("print('hello'); raise SystemExit(3)"))
        supervisor = Supervisor([service], out=out, backoff_start=0.05, max_failures=2, color=False)
        self.assertEqual(supervisor.run(poll=0.02), 1)
        text = out.getvalue()
        self.assertIn("crashy | hello", text)
        self.assertEqual(service.exit_codes, [3, 3, 3])  # 1 start + 2 restart
        self.assertIn("restarting in 0.05 s", text)
        self.assertIn("restarting in 0.1 s", text)       # jeda bertambah dua kali lipat
        self.assertIn("gave up after 2 quick restarts", text)

    def test_no_restart(self):
        out = io.StringIO()
        service = Service("once", python("raise SystemExit(0)"))
        supervisor = Supervisor([service], out=out, restart=False, color=False)
        self.assertEqual(supervisor.run(poll=0.02), 1)
        self.assertEqual(service.exit_codes, [0])

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX only")
    def test_stop_all_stops_children_and_grandchildren(self):
        # Layanan yang punya anak sendiri, seperti runserver dengan auto-reload.
        code = (
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(60)\n"
        )
        out = io.StringIO()
        service = Service("parent", python(code))
        supervisor = Supervisor([service], out=out, stop_timeout=2, color=False)
        supervisor.start(service)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not re.search(r"parent \| (\d+)$", out.getvalue(), re.M):
            time.sleep(0.05)
        grandchild = int(re.search(r"parent \| (\d+)$", out.getvalue(), re.M).group(1))
        supervisor.stop_all()
        self.assertFalse(service.running)
        time.sleep(0.2)
        self.assertFalse(alive(grandchild))


SECRET = "s" * 40


def relay_config(**overrides):
    return Config(**{"port": 0, "shared_secret": SECRET,
                     "redeem_url": "http://127.0.0.1:9000/internal/relay/redeem/", **overrides})


@override_settings(RELAY_PUBLIC_URL="ws://127.0.0.1:8003/relay/")
class RunallCommandTests(SimpleTestCase):
    def preflight(self, names, addrport="127.0.0.1:9000", explicit=frozenset(), **config):
        command = runall.Command(stdout=io.StringIO())
        with mock.patch.object(runall, "relay_config", return_value=relay_config(**config)), \
                mock.patch.object(runall, "port_in_use", return_value=False):
            return command.preflight(names, addrport, explicit=set(explicit)), command.stdout._out.getvalue()

    def test_unknown_service(self):
        with self.assertRaisesMessage(CommandError, "Unknown service: nope"):
            call_command("runall", only="web,nope", stdout=io.StringIO())

    def test_busy_port_is_reported(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            with self.assertRaisesMessage(CommandError, f"Port {port} is already in use"):
                call_command("runall", f"127.0.0.1:{port}", only="web", stdout=io.StringIO())

    def test_relay_ready(self):
        names, out = self.preflight(["web", "relay"])
        self.assertEqual((names, out), (["web", "relay"], ""))

    def test_relay_skipped_with_reason_unless_asked_for(self):
        names, out = self.preflight(["web", "relay"], shared_secret="short")
        self.assertEqual(names, ["web"])
        self.assertIn("Skipping relay: RELAY_SHARED_SECRET", out)
        with self.assertRaisesMessage(CommandError, "Cannot run relay"):
            self.preflight(["relay"], explicit={"relay"}, shared_secret="short")
        with override_settings(RELAY_PUBLIC_URL=""):
            self.assertIn("RELAY_PUBLIC_URL is empty", self.preflight(["relay"])[1])

    def test_redeem_url_on_another_port_is_warned(self):
        names, out = self.preflight(["web", "relay"], redeem_url="http://127.0.0.1:8002/internal/relay/redeem/")
        self.assertEqual(names, ["web", "relay"])
        self.assertIn("RELAY_REDEEM_URL points to port 8002", out)

    def test_builds_one_process_per_service(self):
        captured = {}

        def fake_run(supervisor, poll=0.2):
            captured["argv"] = [s.argv[1:] for s in supervisor.services]
            captured["pythonpath"] = supervisor.env["PYTHONPATH"]
            return 0

        with mock.patch.object(runall, "relay_config", return_value=relay_config()), \
                mock.patch.object(Supervisor, "run", fake_run), \
                mock.patch.object(runall.Command, "single_instance_lock"):
            call_command("runall", "127.0.0.1:0", stdout=io.StringIO())
        self.assertEqual(captured["argv"][0][1:], ["runserver", "127.0.0.1:0"])
        self.assertEqual(captured["argv"][1], ["-m", "relay"])
        self.assertTrue(captured["pythonpath"].startswith(str(runall.settings.BASE_DIR)))
