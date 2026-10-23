"""
Relay WebSocket -> TCP: satu koneksi browser = satu koneksi TCP/TLS ke broker.

Urutan untuk setiap koneksi (Relay.handle):

    1. tukar tiket di Django            gagal -> tutup 4401
    2. batas koneksi per pengguna/total  penuh -> tutup 4429 / 1013
    3. tunggu frame pertama: CONNECT?    bukan -> tutup 4400
    4. periksa dan resolve alamat        dilarang -> 4403, tidak ditemukan -> 4408
    5. buka TCP (dan TLS) ke broker      gagal -> 4408, TLS gagal -> 4495
    6. teruskan byte dua arah, dengan batas laju, batas diam, dan batas umur

Kegagalan di langkah 2–5 dilaporkan ke Django, supaya browser bisa menampilkan alasannya.
Setiap koneksi dicatat (pengguna, tujuan, durasi, jumlah byte), TANPA isi pesan.
"""
import asyncio
import json
import logging
import ssl
import time
import urllib.error
import urllib.request

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from .addresses import Refused, Unreachable, resolve_allowed
from .mqtt import is_connect_packet

log = logging.getLogger("relay")

# Kode penutupan WebSocket (4000-4999 bebas dipakai aplikasi).
BAD_REQUEST, TICKET_INVALID, REFUSED, UNREACHABLE, TOO_MANY, TLS_FAILED = 4400, 4401, 4403, 4408, 4429, 4495
TRY_AGAIN_LATER = 1013

# Permintaan HTTP ke Django TANPA proxy (variabel HTTP(S)_PROXY diabaikan): selalu ke 127.0.0.1.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post_json(url, secret, payload, timeout=5):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Relay-Secret": secret},
    )
    try:
        with _opener.open(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, {}


class Failure(Exception):
    def __init__(self, code, failure, detail=""):
        super().__init__(detail or failure)
        self.code, self.failure, self.detail = code, failure, detail


class Bucket:
    """Batas laju sederhana ("token bucket"): rata-rata `rate` byte per detik."""

    def __init__(self, rate):
        self.rate = rate
        self.tokens = rate
        self.stamp = time.monotonic()

    async def take(self, amount):
        now = time.monotonic()
        self.tokens = min(self.rate, self.tokens + (now - self.stamp) * self.rate)
        self.stamp = now
        self.tokens -= amount
        if self.tokens < 0:
            await asyncio.sleep(-self.tokens / self.rate)


class Relay:
    def __init__(self, config, redeem=None, report=None):
        self.config = config
        # Bisa diganti tiruan di tes; bawaannya memanggil Django.
        self.redeem = redeem or self._redeem
        self.report = report or self._report
        self.per_user = {}
        self.total = 0

    # ------------------------------------------------------------------ Django
    async def _redeem(self, ticket):
        status, data = await asyncio.to_thread(
            post_json, self.config.redeem_url, self.config.shared_secret, {"ticket": ticket})
        return data if status == 200 else None

    async def _report(self, ticket, failure, detail):
        try:
            await asyncio.to_thread(post_json, self.config.report_url, self.config.shared_secret,
                                    {"ticket": ticket, "failure": failure, "detail": detail})
        except OSError:
            log.warning("could not report failure %s to Django", failure)

    # ------------------------------------------------------------------ server
    def process_request(self, connection, request):
        """Tolak alamat selain /relay/<tiket> sebelum jabat tangan WebSocket."""
        prefix = self.config.path_prefix
        if not request.path.startswith(prefix) or len(request.path) <= len(prefix):
            return connection.respond(404, "Not found\n")
        return None

    async def serve(self):
        config = self.config
        async with serve(
            self.handle, config.bind, config.port,
            subprotocols=["mqtt"],
            process_request=self.process_request,
            origins=config.origins or None,
            max_size=config.max_frame,
            server_header=None,
        ) as server:
            log.info("relay listening on %s:%s (ports %s, allow_local=%s)", config.bind, config.port,
                     sorted(config.allowed_ports), config.allow_local)
            await server.serve_forever()

    # ------------------------------------------------------------------ satu koneksi
    async def handle(self, websocket):
        ticket = websocket.request.path[len(self.config.path_prefix):].split("?")[0]
        if websocket.subprotocol != "mqtt":
            await websocket.close(BAD_REQUEST, "MQTT subprotocol required")
            return
        target = await self.redeem(ticket)
        if not target:
            await websocket.close(TICKET_INVALID, "ticket invalid or expired")
            return

        user = target["user_id"]
        if self.per_user.get(user, 0) >= self.config.max_per_user:
            await self.fail(websocket, ticket, Failure(TOO_MANY, "too_many"))
            return
        if self.total >= self.config.max_total:
            await self.fail(websocket, ticket, Failure(TRY_AGAIN_LATER, "busy"))
            return
        self.per_user[user] = self.per_user.get(user, 0) + 1
        self.total += 1
        stats = {"up": 0, "down": 0, "start": time.monotonic(), "reason": "closed", "ip": "-"}
        destination = f"{target['host']}:{target['port']}"
        try:
            await self.relay(websocket, ticket, target, stats)
        except Failure as failure:
            stats["reason"] = failure.failure
            await self.fail(websocket, ticket, failure)
        finally:
            self.per_user[user] -= 1
            if not self.per_user[user]:
                del self.per_user[user]
            self.total -= 1
            log.info("user=%s(%s) to=%s ip=%s tls=%s %.0fs up=%dB down=%dB reason=%s",
                     target["username"], user, destination, stats["ip"], target["tls"],
                     time.monotonic() - stats["start"], stats["up"], stats["down"], stats["reason"])

    async def fail(self, websocket, ticket, failure):
        await self.report(ticket, failure.failure, failure.detail)
        try:
            await websocket.close(failure.code, failure.failure)
        except ConnectionClosed:
            pass

    async def relay(self, websocket, ticket, target, stats):
        config = self.config
        # 3. Frame pertama harus paket MQTT CONNECT: relay bukan terowongan TCP umum.
        try:
            first = await asyncio.wait_for(websocket.recv(), config.first_frame_timeout)
        except (asyncio.TimeoutError, ConnectionClosed):
            raise Failure(BAD_REQUEST, "bad_request", "no CONNECT packet received")
        if not isinstance(first, bytes) or not is_connect_packet(first):
            raise Failure(BAD_REQUEST, "bad_request", "the first packet is not MQTT CONNECT")

        # 4. Alamat tujuan.
        host, port = target["host"], int(target["port"])
        try:
            ip = await resolve_allowed(host, port, config)
        except Refused as exc:
            raise Failure(REFUSED, "address_not_allowed", str(exc))
        except Unreachable as exc:
            raise Failure(UNREACHABLE, "unreachable", str(exc))
        stats["ip"] = ip

        # 5. Koneksi ke broker: ke IP yang SUDAH diperiksa; nama host hanya untuk TLS (SNI + sertifikat).
        context = None
        if target["tls"]:
            context = ssl.create_default_context()
            # CA sendiri dari profil (tahap M6), DITAMBAHKAN ke daftar CA sistem; nama host tetap diperiksa.
            if target.get("ca_pem"):
                try:
                    context.load_verify_locations(cadata=target["ca_pem"])
                except (ssl.SSLError, ValueError):
                    raise Failure(TLS_FAILED, "tls_failed", "the custom CA certificate is not valid")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, ssl=context, server_hostname=host if context else None),
                config.connect_timeout,
            )
        except ssl.SSLError as exc:
            raise Failure(TLS_FAILED, "tls_failed", getattr(exc, "reason", None) or str(exc)[:150])
        except (OSError, asyncio.TimeoutError) as exc:
            raise Failure(UNREACHABLE, "unreachable", str(exc)[:150] or "timed out")

        # 6. Teruskan byte dua arah.
        last_activity = time.monotonic()
        up, down = Bucket(config.rate_bytes), Bucket(config.rate_bytes)

        async def browser_to_broker():
            nonlocal last_activity
            message = first
            while True:
                if not isinstance(message, bytes):
                    return "text frame"
                await up.take(len(message))
                writer.write(message)
                await writer.drain()
                stats["up"] += len(message)
                last_activity = time.monotonic()
                try:
                    message = await websocket.recv()
                except ConnectionClosed:
                    return "browser closed"

        async def broker_to_browser():
            nonlocal last_activity
            while True:
                data = await reader.read(65536)
                if not data:
                    return "broker closed"
                await down.take(len(data))
                try:
                    await websocket.send(data)
                except ConnectionClosed:
                    return "browser closed"
                stats["down"] += len(data)
                last_activity = time.monotonic()

        async def watchdog():
            while True:
                await asyncio.sleep(min(5, config.idle_seconds))
                if time.monotonic() - last_activity > config.idle_seconds:
                    return "idle timeout"

        tasks = [asyncio.create_task(job()) for job in (browser_to_broker, broker_to_browser, watchdog)]
        try:
            done, _ = await asyncio.wait(tasks, timeout=config.max_seconds, return_when=asyncio.FIRST_COMPLETED)
            stats["reason"] = next(iter(done)).result() if done else "max lifetime"
        except (OSError, ConnectionError) as exc:
            stats["reason"] = f"error: {exc}"[:80]
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass
            try:
                await websocket.close(1000 if stats["reason"] in ("broker closed", "browser closed") else 1001)
            except ConnectionClosed:
                pass
