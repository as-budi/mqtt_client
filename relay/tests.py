"""
Tes relay (tahap M4). Dijalankan bersama tes Django: `python manage.py test`.

Broker tiruan (TCP di 127.0.0.1) menjawab CONNECT dengan CONNACK dan memantulkan paket
lain. Penukaran tiket ke Django juga ditiru. Karena broker tiruan ada di localhost, tes
integrasi memakai allow_local=True; pemblokiran localhost diuji terpisah.
"""
import asyncio
import shutil
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .addresses import Refused, ip_allowed, resolve_allowed
from .config import Config
from .mqtt import is_connect_packet
from .server import Relay

# CONNECT MQTT 3.1.1, client id "t": 0x10, panjang 13, "MQTT", level 4, flag clean, keepalive 60.
CONNECT = bytes([0x10, 13, 0, 4]) + b"MQTT" + bytes([4, 2, 0, 60, 0, 1]) + b"t"
CONNACK = bytes([0x20, 2, 0, 0])
PINGREQ = bytes([0xC0, 0])


class PacketTests(unittest.TestCase):
    def test_connect_detection(self):
        self.assertTrue(is_connect_packet(CONNECT))
        self.assertTrue(is_connect_packet(bytes([0x10, 12, 0, 6]) + b"MQIsdp" + bytes([3, 2, 0, 60])))
        self.assertFalse(is_connect_packet(b"GET / HTTP/1.1\r\n"))
        self.assertFalse(is_connect_packet(PINGREQ))
        self.assertFalse(is_connect_packet(bytes([0x10, 6, 0, 4]) + b"HTTP"))
        self.assertFalse(is_connect_packet(bytes([0x10, 0xFF, 0xFF, 0xFF, 0xFF, 0x7F])))


class AddressTests(unittest.IsolatedAsyncioTestCase):
    def test_public_and_private_addresses(self):
        for ip in ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"]:
            self.assertTrue(ip_allowed(ip), ip)
        for ip in ["127.0.0.1", "10.1.2.3", "172.16.5.4", "192.168.1.10", "169.254.169.254", "100.64.0.1",
                   "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:10.0.0.1", "::ffff:127.0.0.1"]:
            self.assertFalse(ip_allowed(ip), ip)

    def test_allow_local_still_blocks_link_local(self):
        self.assertTrue(ip_allowed("127.0.0.1", allow_local=True))
        self.assertTrue(ip_allowed("192.168.1.10", allow_local=True))
        self.assertFalse(ip_allowed("169.254.169.254", allow_local=True))

    async def test_resolve_rules(self):
        config = Config(deny_hosts=["bad.example.com"])
        with self.assertRaisesRegex(Refused, "port 22"):
            await resolve_allowed("broker.example.com", 22, config)
        with self.assertRaisesRegex(Refused, "blocked"):
            await resolve_allowed("x.bad.example.com", 1883, config)
        with self.assertRaisesRegex(Refused, "private"):
            await resolve_allowed("localhost", 1883, config)
        with self.assertRaisesRegex(Refused, "private"):
            await resolve_allowed("127.0.0.1", 8883, config)


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = []

        async def broker(reader, writer):
            data = await reader.read(1024)
            self.received.append(data)
            writer.write(CONNACK)
            await writer.drain()
            while data := await reader.read(1024):
                self.received.append(data)
                writer.write(data)          # pantulkan
                await writer.drain()
            writer.close()

        self.broker = await asyncio.start_server(broker, "127.0.0.1", 0)
        self.broker_port = self.broker.sockets[0].getsockname()[1]
        self.reports = []
        self.tickets = {"good": {"ticket_id": 1, "user_id": 7, "username": "budi", "host": "127.0.0.1",
                                 "port": self.broker_port, "tls": False}}

        async def redeem(ticket):
            return self.tickets.pop(ticket, None)

        async def report(ticket, failure, detail):
            self.reports.append((ticket, failure, detail))

        self.config = Config(bind="127.0.0.1", port=0, allowed_ports={self.broker_port}, allow_local=True,
                             first_frame_timeout=2, max_per_user=1)
        self.relay = Relay(self.config, redeem=redeem, report=report)
        from websockets.asyncio.server import serve
        self.server = await serve(self.relay.handle, "127.0.0.1", 0, subprotocols=["mqtt"],
                                  process_request=self.relay.process_request)
        self.url = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/relay/"

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.broker.close()
        await self.broker.wait_closed()

    async def closed_with(self, websocket):
        with self.assertRaises(ConnectionClosed) as caught:
            for _ in range(5):
                await asyncio.wait_for(websocket.recv(), 3)
        return caught.exception.rcvd.code

    async def test_bytes_flow_both_ways(self):
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            self.assertEqual(await asyncio.wait_for(websocket.recv(), 3), CONNACK)
            await websocket.send(PINGREQ)
            self.assertEqual(await asyncio.wait_for(websocket.recv(), 3), PINGREQ)
        self.assertEqual(self.received[0], CONNECT)
        self.assertEqual(self.reports, [])

    async def test_invalid_ticket(self):
        async with connect(self.url + "nope", subprotocols=["mqtt"]) as websocket:
            self.assertEqual(await self.closed_with(websocket), 4401)

    async def test_first_packet_must_be_connect(self):
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(b"SSH-2.0-OpenSSH\r\n")
            self.assertEqual(await self.closed_with(websocket), 4400)
        self.assertEqual(self.reports[0][1], "bad_request")
        self.assertEqual(self.received, [])          # tidak ada yang sampai ke broker

    async def test_private_address_refused_in_production_mode(self):
        self.config.allow_local = False
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            self.assertEqual(await self.closed_with(websocket), 4403)
        self.assertEqual(self.reports[0][1], "address_not_allowed")
        self.assertEqual(self.received, [])

    async def test_port_not_allowed(self):
        self.config.allowed_ports = {1883}
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            self.assertEqual(await self.closed_with(websocket), 4403)
        self.assertIn("port", self.reports[0][2])

    async def test_unreachable_broker(self):
        self.broker.close()
        await self.broker.wait_closed()
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            self.assertEqual(await self.closed_with(websocket), 4408)
        self.assertEqual(self.reports[0][1], "unreachable")

    async def test_connection_limit_per_user(self):
        self.tickets["second"] = dict(self.tickets["good"])
        async with connect(self.url + "good", subprotocols=["mqtt"]) as first:
            await first.send(CONNECT)
            await asyncio.wait_for(first.recv(), 3)
            async with connect(self.url + "second", subprotocols=["mqtt"]) as second:
                self.assertEqual(await self.closed_with(second), 4429)
        self.assertEqual(self.reports[0][1], "too_many")

    async def test_wrong_path_is_404(self):
        with self.assertRaises(Exception):
            async with connect(self.url.replace("/relay/", "/other/") + "x", subprotocols=["mqtt"]):
                pass


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a test certificate")
class TlsRelayTests(RelayTests):
    """Broker mqtts dengan sertifikat self-signed: hanya bisa dipakai bila CA-nya diberikan (tahap M6)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                        "-keyout", str(folder / "key.pem"), "-out", str(folder / "cert.pem")],
                       check=True, capture_output=True)
        cls.cert = folder / "cert.pem"
        cls.key = folder / "key.pem"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        super().tearDownClass()

    async def asyncSetUp(self):
        await super().asyncSetUp()
        # Handshake yang sengaja gagal tidak perlu dicetak asyncio sebagai error.
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: None)
        # Ganti broker tiruan dengan versi TLS di port baru.
        self.broker.close()
        await self.broker.wait_closed()
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.cert, self.key)

        async def broker(reader, writer):
            data = await reader.read(1024)
            self.received.append(data)
            writer.write(CONNACK)
            await writer.drain()
            writer.close()

        self.broker = await asyncio.start_server(broker, "127.0.0.1", 0, ssl=server_context)
        port = self.broker.sockets[0].getsockname()[1]
        self.config.allowed_ports = {port}
        self.tickets["good"].update(port=port, tls=True)

    async def test_self_signed_refused_without_ca(self):
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            await self.closed_with(websocket)
        self.assertEqual(self.reports[0][1], "tls_failed")

    async def test_custom_ca_accepted(self):
        self.tickets["good"]["ca_pem"] = self.cert.read_text()
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            self.assertEqual(await asyncio.wait_for(websocket.recv(), 3), CONNACK)
        self.assertEqual(self.received[0], CONNECT)

    async def test_invalid_ca(self):
        self.tickets["good"]["ca_pem"] = "-----BEGIN CERTIFICATE-----\nnot base64\n-----END CERTIFICATE-----\n"
        async with connect(self.url + "good", subprotocols=["mqtt"]) as websocket:
            await websocket.send(CONNECT)
            await self.closed_with(websocket)
        self.assertEqual(self.reports[0], ("good", "tls_failed", "the custom CA certificate is not valid"))

    # Tes plain-TCP dari RelayTests tidak berlaku untuk broker TLS ini.
    test_bytes_flow_both_ways = None
    test_unreachable_broker = None
    test_connection_limit_per_user = None
    test_port_not_allowed = None
    test_private_address_refused_in_production_mode = None
    test_first_packet_must_be_connect = None
    test_invalid_ticket = None
    test_wrong_path_is_404 = None
