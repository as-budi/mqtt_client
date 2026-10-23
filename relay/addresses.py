"""
Alamat broker yang boleh dituju relay (mencegah SSRF).

Tanpa pembatasan, relay bisa dipakai untuk menjangkau layanan DI DALAM server sendiri atau
jaringan lokalnya: Mosquitto 127.0.0.1:1883 milik bridge platform, MySQL, Redis, atau
alamat metadata cloud 169.254.169.254. Aturannya:

    1. port harus ada di RELAY_ALLOWED_PORTS (bawaan 1883 dan 8883);
    2. host tidak ada di RELAY_DENY_HOSTS;
    3. nama host di-resolve OLEH RELAY, dan SEMUA alamat hasilnya harus IP publik
       (bukan loopback, privat 10/8 172.16/12 192.168/16, link-local, CGNAT 100.64/10,
       multicast, atau padanannya di IPv6);
    4. koneksi dibuka ke IP yang sudah diperiksa itu, BUKAN dengan resolve ulang, supaya
       DNS yang berganti jawaban di tengah jalan ("DNS rebinding") tidak bisa mengecoh.

RELAY_ALLOW_LOCAL=True (khusus laptop) mengizinkan localhost dan LAN, misalnya Mosquitto di
komputer sendiri. Link-local (termasuk alamat metadata cloud) tetap ditolak.
"""
import asyncio
import ipaddress
import socket


class Refused(Exception):
    """Alamat tidak boleh dituju."""


class Unreachable(Exception):
    """Nama host tidak ditemukan."""


def ip_allowed(ip, allow_local=False):
    address = ipaddress.ip_address(ip.split("%")[0])
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_multicast or address.is_unspecified or address.is_link_local or address.is_reserved:
        return False
    if allow_local and (address.is_private or address.is_loopback):
        return True
    return address.is_global


def host_denied(host, deny_hosts):
    host = host.lower().rstrip(".")
    return any(host == denied or host.endswith("." + denied) for denied in deny_hosts)


async def resolve_allowed(host, port, config):
    """IP yang aman untuk dituju, atau Refused / Unreachable."""
    if port not in config.allowed_ports:
        allowed = ", ".join(str(p) for p in sorted(config.allowed_ports))
        raise Refused(f"port {port} is not allowed (allowed: {allowed})")
    if host_denied(host, config.deny_hosts):
        raise Refused(f"{host} is blocked on this server")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Unreachable(f"{host} was not found") from exc
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise Unreachable(f"{host} was not found")
    if not all(ip_allowed(ip, config.allow_local) for ip in addresses):
        raise Refused(f"{host} resolves to a private or reserved address")
    return addresses[0]
