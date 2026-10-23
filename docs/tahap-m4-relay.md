# Tahap M4: Relay WebSocket → TCP untuk broker `mqtt://` dan `mqtts://`

Browser hanya bisa membuka WebSocket, tidak bisa membuka koneksi TCP biasa. Broker yang hanya
membuka port 1883 atau 8883 (misalnya Mosquitto standar, atau broker IoT Platform lewat
`mqtts://`) dijangkau lewat **relay** di server aplikasi ini.

```
browser (mqtt.js) ══ wss://mqtt.domain/relay/<tiket> ══▶ relay :8003 ── TCP/TLS ──▶ broker:1883/8883
     │                                                       │
     └── POST /connections/<pk>/connect/ ─▶ Django ◀── POST /internal/relay/redeem/ (tiket → tujuan)
```

Relay hanya **meneruskan byte**. Ia tidak memahami topik atau pesan; protokol MQTT tetap
dijalankan mqtt.js di browser, sama persis dengan jalur Direct. Semua fitur M3 otomatis bekerja
di kedua jalur.

## 1. Alur satu koneksi

1. Browser meminta bahan connect. Django memeriksa pengguna dan profil, lalu membuat **tiket**:
   - acak 32 byte, berlaku 60 detik, sekali pakai;
   - database hanya menyimpan hash-nya (model `RelayTicket`);
   - tujuan (host, port, TLS) disimpan di tiket, **bukan** dikirim browser ke relay.
2. mqtt.js membuka `wss://…/relay/<tiket>` dengan subprotokol `mqtt`.
3. Relay menukarkan tiket di `POST /internal/relay/redeem/`. Penukarannya adalah satu
   `UPDATE … WHERE used_at IS NULL`, jadi tiket tidak bisa dipakai dua kali.
4. Relay menunggu frame pertama dan memeriksa bahwa isinya **paket MQTT CONNECT**.
5. Relay memeriksa alamat tujuan, lalu membuka TCP (dan TLS) ke broker.
6. Byte diteruskan dua arah sampai salah satu menutup koneksi.

Bila gagal di langkah 3–5, relay menutup WebSocket dengan kode khusus dan melaporkan alasannya ke
Django (`/internal/relay/report/`). Browser lalu menanyakan
`/connections/relay/<id>/status/` dan menampilkan pesan yang jelas:

| Kode | Alasan | Pesan di browser | Dicoba lagi? |
|---|---|---|---|
| 4401 | tiket salah/kedaluwarsa | ticket expired | ya (tiket baru) |
| 4400 | bukan paket CONNECT | not an MQTT connection | tidak |
| 4403 | alamat atau port dilarang | may not connect to this address (+ rincian, mis. "port 22 is not allowed") | tidak |
| 4408 | broker tidak terjangkau | could not be reached | ya |
| 4495 | TLS gagal | TLS handshake failed (self-signed?) | tidak |
| 4429 | terlalu banyak koneksi pengguna ini | too many relay connections | ya |
| 1013 | relay penuh | relay is busy | ya |

## 2. Mengapa relay perlu dikunci rapat

Relay membuat **server** membuka koneksi ke alamat yang dipilih pengguna. Tanpa pembatasan,
relay bisa dipakai untuk:

- menjangkau layanan internal server (*SSRF*): Mosquitto `127.0.0.1:1883` milik bridge
  platform, MySQL, Redis, alamat metadata cloud `169.254.169.254`;
- menjadi terowongan TCP umum: mengirim spam ke port 25, mencoba SSH ke server lain atas nama IP
  VPS.

Pengamannya:

| Lapisan | Rincian | Kode |
|---|---|---|
| Login + tiket | hanya pengguna yang login; tujuan dari tiket buatan Django | `connections/session.py`, `relay_api.py` |
| Hanya MQTT | frame pertama harus CONNECT (`0x10` + nama protokol `MQTT`/`MQIsdp`) | `relay/mqtt.py` |
| Port | hanya `RELAY_ALLOWED_PORTS` (bawaan 1883, 8883) | `relay/addresses.py` |
| Alamat IP | host di-resolve relay; **semua** hasilnya harus IP publik (bukan loopback, 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10, multicast, padanannya di IPv6) | `relay/addresses.py` |
| DNS rebinding | koneksi dibuka ke IP yang sudah diperiksa, bukan resolve ulang; nama host hanya untuk TLS (SNI + sertifikat) | `relay/server.py` |
| Kernel | `IPAddressDeny=` jaringan privat di unit systemd | `deploy/systemd/mqttc-relay.service` |
| Batas | 5 koneksi per pengguna, 200 total, 20 tiket/menit per pengguna, 64 KB/s per arah, frame 256 KB, diam 10 menit, umur 12 jam | `relay/config.py`, settings |
| Endpoint internal | header `X-Relay-Secret`; permintaan lewat Nginx (`X-Forwarded-For`) ditolak; Nginx menjawab 404 untuk `/internal/` | `connections/relay_api.py`, `deploy/nginx/relay-locations.conf` |
| Log | pengguna, tujuan, IP, durasi, jumlah byte, alasan putus; **tanpa** isi pesan | `relay/server.py` |

TLS ke broker (`mqtts://`) diperiksa dengan daftar CA sistem. Sertifikat self-signed ditolak; CA
sendiri dan mTLS direncanakan di M6.

Relay melihat byte yang lewat, termasuk password di paket CONNECT. Relay tidak menyimpan atau
mencatatnya, dan kodenya kecil supaya mudah diperiksa. Untuk broker IoT Platform, jalur Direct
(`wss://`) tetap lebih disarankan.

## 3. Program relay

Paket `relay/` sengaja **tanpa Django**: Python asyncio + pustaka `websockets`, sekitar 300
baris.

```
relay/__main__.py    python -m relay
relay/config.py      pengaturan dari .env (RELAY_*)
relay/mqtt.py        mengenali paket CONNECT
relay/addresses.py   aturan alamat (SSRF)
relay/server.py      tiket, batas, koneksi ke broker, penerus byte
relay/tests.py       12 tes (broker tiruan; ikut `python manage.py test`)
```

Pengaturan (di `.env` yang sama dengan Django):

| Nama | Laptop | Server |
|---|---|---|
| `RELAY_PUBLIC_URL` (Django) | `ws://127.0.0.1:8003/relay/` | `wss://mqtt.domain/relay/` |
| `RELAY_SHARED_SECRET` | acak 32+ karakter | acak 32+ karakter (wajib) |
| `RELAY_REDEEM_URL`, `RELAY_REPORT_URL` | `http://127.0.0.1:9000/internal/relay/...` | `http://127.0.0.1:8002/internal/relay/...` |
| `RELAY_ALLOW_LOCAL` | `True` (boleh ke Mosquitto di laptop/LAN) | **`False`** |
| `RELAY_ALLOWED_PORTS` | `1883,8883` | `1883,8883` |
| `RELAY_ORIGINS` | kosong | `https://mqtt.domain` |

## 4. Mencoba di laptop

```bash
# terminal 1: aplikasi (port 9000), terminal 2: relay
python manage.py runserver 127.0.0.1:9000
python -m relay        # INFO relay: relay listening on 127.0.0.1:8003 (ports [1883, 8883], allow_local=True)
```

Lalu buat profil, misalnya `mqtt://broker.hivemq.com:1883`, atau Mosquitto lokal
`mqtt://127.0.0.1:1883` (butuh `RELAY_ALLOW_LOCAL=True`). Profil itu berlabel **Relay**.
**Connect** seperti biasa. Setiap koneksi tercatat di terminal relay:

```
INFO relay: user=rina(1) to=127.0.0.1:1883 ip=127.0.0.1 tls=False 12s up=68B down=33B reason=browser closed
```

Coba juga port lain, misalnya `mqtt://127.0.0.1:2883`. Relay menolak dan halaman menampilkan
"port 2883 is not allowed", tanpa mengulang.

## 5. Di server

Unit `deploy/systemd/mqttc-relay.service` dan potongan Nginx `deploy/nginx/relay-locations.conf`
sudah disiapkan. Pemasangan lengkap (user `mqttc`, Gunicorn, Nginx, sertifikat) dikerjakan di
tahap M7.
