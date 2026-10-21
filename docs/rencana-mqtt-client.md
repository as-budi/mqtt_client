# Rencana: Aplikasi MQTT Client Web (`mqtt.reslab-csub.cloud`)

Status: **rencana**, belum dikerjakan. Repo: `mqtt_client` (platform: repo `IoT_platform`). Dokumen ini merancang aplikasi MQTT client berbasis web
yang melengkapi IoT platform: untuk menguji device, mensimulasikan device, dan belajar MQTT
tanpa memasang aplikasi apa pun di laptop.

Keputusan (2026-10-21, direvisi hari yang sama):

| Pertanyaan | Pilihan |
|---|---|
| Broker yang boleh disambungkan | **Bebas**: broker WebSocket (`ws`/`wss`) **dan** broker TCP biasa (`mqtt://` 1883, `mqtts://` 8883), ditambah profil siap pakai untuk broker platform |
| Akun | **Login memakai akun IoT platform** (OAuth 2.0 / OpenID Connect); sign up dilakukan di platform |
| Tempat protokol MQTT dijalankan | **Di browser** (mqtt.js). Broker WebSocket disambung langsung; broker TCP lewat **relay** di server |
| Domain platform | `iot.reslab-csub.cloud` (sebelumnya `iot.reslab.cloud`) |
| Server | **VPS yang sama** dengan platform |
| Repo | **repo terpisah** `mqtt_client`, folder bersebelahan dengan `IoT_platform`; dokumen tahap di `docs/` repo ini |

---

## 1. Gambaran umum

Aplikasi ini bekerja seperti MQTTX Web atau HiveMQ WebSocket Client:

- buat profil koneksi,
- sambungkan ke broker,
- subscribe topik dan lihat pesan yang masuk,
- publish pesan.

Bedanya, aplikasi ini terhubung dengan IoT platform:

- login memakai akun platform;
- device milik pengguna bisa langsung dipakai sebagai profil koneksi;
- topik platform (`telemetry`, `desired`, `commands/+`, …) tersedia sebagai templat;
- ada simulator device untuk menguji aturan, dashboard, dan OTA tanpa ESP32.

### 1.1 Dua jalur koneksi

Browser hanya bisa membuka WebSocket, tidak bisa membuka koneksi TCP biasa. Karena itu ada dua
jalur. Jalurnya dipilih otomatis dari skema alamat broker di profil.

| Skema di profil | Jalur | Contoh |
|---|---|---|
| `wss://` (dan `ws://` saat lokal) | **Direct**: browser langsung ke broker | `wss://iot.reslab-csub.cloud/mqtt`, `wss://broker.emqx.io:8084/mqtt` |
| `mqtt://`, `mqtts://` | **Relay**: browser → WebSocket ke relay di VPS → TCP/TLS ke broker | `mqtts://iot.reslab-csub.cloud:8883`, `mqtt://broker.hivemq.com:1883` |

```
                    ┌────────────────── VPS yang sama ──────────────────────────┐
                    │                                                           │
   login (redirect) │  iot.reslab-csub.cloud          mqtt.reslab-csub.cloud    │
 ┌─────────────────▶│  platform (Daphne :8001)  ◀───  aplikasi client           │
 │                  │  OIDC provider, API device  API (Gunicorn :8002)          │
 │                  │  Mosquitto :8883, ws :9001      relay (:8003)  ───────────┼──▶ broker TCP
 │                  │        ▲                          ▲                       │    lain
 │                  └────────┼──────────────────────────┼───────────────────────┘    (1883/8883)
 │                           │ wss://…/mqtt             │ wss://mqtt…/relay
┌┴─────────────────────┐     │ (direct)                 │ (relay)
│ Browser pengguna     ├─────┴──────────────────────────┘
│ halaman + mqtt.js    ├────────────────────────────────────────────▶ broker WebSocket lain
└──────────────────────┘          wss:// (direct)                     (mis. broker.emqx.io:8084)
```

**Prinsip utama:** protokol MQTT selalu dijalankan mqtt.js di browser. Relay hanya
**penerus byte** antara WebSocket dan TCP; ia tidak memahami topik atau pesan. Akibatnya:

- semua fitur (subscribe, publish, MQTT 5, simulator) hanya ditulis sekali, di JavaScript, dan
  bekerja sama persis di kedua jalur;
- server tidak menyimpan pesan, sesi MQTT, maupun password broker;
- koneksi hidup selama tab browser terbuka (lihat bagian 10).

Alternatif yang **tidak** dipilih: server menjalankan klien MQTT sendiri (paho) dan meneruskan
pesan ke browser lewat Channels. Cara ini membuat setiap fitur ditulis dua kali (Python dan
JavaScript), server memegang sesi semua pengguna, dan perilaku kedua jalur bisa berbeda.

---

## 2. Fitur

Prioritas: **M** = wajib di versi pertama (MVP), **L** = lanjutan.

### 2.1 Akun

| Fitur | Prioritas |
|---|---|
| *Sign in with IoT Platform*: tombol login mengarah ke halaman login platform, lalu kembali | M |
| *Create account*: tautan ke halaman Sign up platform (aktivasi email tetap di platform), lalu kembali ke aplikasi | M |
| Layar persetujuan (*consent*) saat pertama kali: aplikasi meminta izin membaca profil dan daftar device | M |
| Logout (aplikasi saja, atau sekaligus dari platform) | M |
| Akun yang dinonaktifkan di platform tidak bisa masuk lagi (dicek saat token diperbarui) | M |
| Halaman *Settings*: tema, batas jumlah pesan, format waktu | L |

### 2.2 Profil koneksi

| Fitur | Prioritas |
|---|---|
| Alamat broker sebagai URL: `mqtt://`, `mqtts://`, `wss://`, `ws://`; host, port (bawaan 1883/8883/443), path WebSocket (`/mqtt`). Jalur Direct/Relay tampil sebagai label | M |
| Client ID (otomatis + awalan), username, password, keep alive, clean start, versi MQTT 3.1.1 / 5.0 | M |
| Last Will: topik, payload, QoS, retain | M |
| Auto reconnect dengan jeda bertambah, tombol Connect/Disconnect, status (connecting, connected, reconnecting, error + pesan error yang jelas, termasuk penolakan relay) | M |
| Beberapa koneksi aktif sekaligus (tab per koneksi) | M |
| Profil bawaan: broker platform (`wss://iot.reslab-csub.cloud/mqtt` dan `mqtts://…:8883`), `broker.emqx.io`, `test.mosquitto.org`, `broker.hivemq.com` | M |
| Profil dari device platform: pilih device → alamat, username/password = access token, dan topik terisi otomatis | M |
| Password **tidak** disimpan di server. Pilihan: tanya setiap connect (bawaan) atau *Remember in this browser* (dengan peringatan) | M |
| TLS untuk `mqtts://`: verifikasi sertifikat dengan CA sistem (bawaan) | M |
| TLS lanjutan untuk `mqtts://`: CA sendiri (tempel PEM, untuk broker lab bersertifikat self-signed), sertifikat klien (mTLS), SNI berbeda | L |
| Ekspor/impor profil sebagai JSON (tanpa password) | L |
| Opsi MQTT 5: session expiry, receive maximum, user properties saat CONNECT | L |

### 2.3 Subscribe

| Fitur | Prioritas |
|---|---|
| Tambah langganan: topic filter (`+`, `#`) dengan validasi sintaks, QoS 0/1/2, warna penanda | M |
| Unsubscribe, jeda (*mute*) satu langganan tanpa unsubscribe | M |
| Langganan disimpan di profil dan dipasang ulang otomatis setelah reconnect | M |
| Langganan yang ditolak broker (SUBACK 0x80, mis. karena ACL) ditampilkan jelas: "Not authorized for this topic" | M |
| Opsi MQTT 5: no local, retain as published, retain handling, subscription identifier | L |

### 2.4 Daftar pesan

| Fitur | Prioritas |
|---|---|
| Daftar pesan masuk dan keluar: waktu, arah, topik, QoS, flag retain, ukuran, payload | M |
| Tampilan payload: teks, JSON rapi berwarna (memakai ulang `json_viewer.js` platform), hex, base64 | M |
| Saring berdasarkan topik, teks payload, arah; jeda gulir otomatis; kosongkan daftar | M |
| Batas pesan di memori (bawaan 2.000 per koneksi; yang lama dibuang) | M |
| Salin topik/payload, *Publish again* dari pesan mana pun | M |
| **Topic tree** ala MQTT Explorer: pohon topik, nilai terakhir, jumlah pesan, waktu terakhir | L |
| Grafik kecil nilai angka per topik/key JSON (mis. `temperature`) | L |
| Ekspor pesan ke CSV/JSON | L |

### 2.5 Publish

| Fitur | Prioritas |
|---|---|
| Form publish: topik, payload, format (text/JSON, dengan validasi dan tombol *Format*), QoS, retain | M |
| Riwayat publish (20 terakhir) dan templat tersimpan (*Saved messages*) | M |
| Hapus pesan retained (publish payload kosong + retain) dengan konfirmasi | M |
| Placeholder dinamis: `{{timestamp}}`, `{{random:20:30}}`, `{{counter}}` | L |
| Publish berulang setiap N detik (simulasi sensor sederhana; minimal 1 detik) | L |
| Properti MQTT 5: content type, response topic, correlation data, message expiry, user properties | L |

### 2.6 Integrasi dengan IoT platform

| Fitur | Prioritas |
|---|---|
| Daftar device milik pengguna, plus device yang dibagikan kepadanya (tahap 19), dari API platform | M |
| Templat topik per device: `<prefix>/<token>/telemetry`, `desired`, `commands/+`, `commands/<id>/response`, `firmware`, `status`, `errors` | M |
| **Simulator device**: kirim telemetri berkala dengan nilai acak dalam rentang `min`/`max` variabel; tombol online/offline (status + Last Will) | L |
| **Auto-responder command**: jawab command (`ping`, `blink`) otomatis dengan respons yang bisa diatur, untuk menguji rule engine dan halaman command | L |
| Simulasi OTA: laporkan versi firmware dan langkah DOWNLOADING → UPDATED (seperti `scripts/fake_mqtt_device.py` di repo platform) | L |
| Tautan *Open in platform* dari device ke halaman device-nya | M |

### 2.7 Tampilan

- Bahasa Inggris, Bootstrap 5.3, tema Light/Dark/Auto seperti platform.
- Tata letak tiga kolom di layar lebar (koneksi | langganan | pesan + publish); di ponsel
  menjadi tab.
- Pintasan keyboard: `Ctrl+Enter` untuk publish, `/` untuk mencari.

---

## 3. Akun: OpenID Connect dengan platform sebagai penyedia

```
Browser          mqtt.reslab-csub.cloud            iot.reslab-csub.cloud
  │ klik "Sign in"      │                                │
  │────────────────────▶│ redirect /o/authorize?          │
  │◀────────────────────│   client_id, PKCE, state, nonce │
  │──────────────────────────────────────────────────────▶│ login (atau Sign up → aktivasi
  │                     │                                │ email → kembali), consent
  │◀──────────────────────────────────────────────────────│ redirect ?code=…
  │────────────────────▶│ tukar code + verifier ─────────▶│ /o/token
  │                     │◀──── id_token, access_token, refresh_token
  │ sesi aplikasi       │ buat/perbarui User lokal (sub, username, email)
```

Kedua aplikasi berada di domain induk yang sama (`reslab-csub.cloud`). Meski begitu, login
tetap lewat OIDC, **bukan** cookie sesi bersama, karena:

- kedua aplikasi tetap terpisah: database, kode, dan rilis masing-masing;
- cookie sesi platform tetap *host-only* (jangan isi `SESSION_COOKIE_DOMAIN`), sehingga
  aplikasi client tidak pernah bisa membaca sesi platform.

**Di platform** (app baru, mis. `oauth`):

- `django-oauth-toolkit` dengan OIDC aktif (kunci RSA untuk menandatangani `id_token`, di
  `.env`).
- Satu aplikasi klien terdaftar: *MQTT Client*, confidential, Authorization Code + PKCE,
  redirect URI tepat `https://mqtt.reslab-csub.cloud/oidc/callback/`.
- Scope: `openid profile email` dan `devices:read` (daftar device beserta access token).
  Token device setara password, jadi layar consent harus menyebutnya dengan jelas.
- Halaman login dan Sign up menerima `next=`, sehingga pengguna baru kembali ke alur OAuth
  setelah aktivasi email.
- API baru yang dilindungi token OAuth (bukan sesi):
  - `GET /api/v2/me` mengembalikan profil;
  - `GET /api/v2/me/devices` mengembalikan device yang terlihat oleh pengguna
    (`visible_devices`): nama, lokasi, variabel, peran (owner/shared), access token, dan alamat
    MQTT publik (`mqtt_info()`).
- Halaman *Profile → Connected apps*: daftar aplikasi yang diberi izin, dengan tombol *Revoke*.

**Di aplikasi client:** `mozilla-django-oidc` (atau Authlib) sebagai relying party.

- User lokal dibuat dari klaim `sub`.
- Access token platform disimpan terenkripsi di sesi server, dipakai server-ke-server untuk
  memanggil API device, dan tidak pernah dikirim ke JavaScript.
- Pemanggilan API dilakukan ke alamat publik `https://iot.reslab-csub.cloud`, bukan ke
  `127.0.0.1:8001`, supaya sertifikat, `ALLOWED_HOSTS`, dan rate limit tetap sama dengan klien
  lain.

---

## 4. Broker platform: listener WebSocket (jalur Direct)

Untuk broker platform, jalur Direct lebih hemat daripada relay. Mosquitto mendapat listener
tambahan yang hanya mendengar di localhost, di belakang Nginx:

```conf
# /etc/mosquitto/conf.d/iot.conf (tambahan)
listener 9001 127.0.0.1
protocol websockets
```

Karena `per_listener_settings false`, akun dan ACL yang sama berlaku: username = password =
access token, dan setiap device hanya bisa memakai topiknya sendiri.

Nginx di `iot.reslab-csub.cloud` (memakai sertifikat yang sudah ada):

```nginx
# di awal file, di luar blok server:
# limit_conn_zone $binary_remote_addr zone=iot_ws:10m;

location = /mqtt {
    limit_conn iot_ws 20;                 # batas koneksi per IP
    proxy_pass http://127.0.0.1:9001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 1h;
}
```

Alamat broker untuk browser menjadi `wss://iot.reslab-csub.cloud/mqtt` (port 443). Port 443
lebih jarang diblokir jaringan kampus daripada 8883. Halaman device di platform (tab MQTT) juga
menampilkan alamat ini.

`mqtts://iot.reslab-csub.cloud:8883` lewat relay tetap bisa dipakai, misalnya untuk meniru
koneksi ESP32 apa adanya.

**Opsi lanjutan (L): sandbox per pengguna.** Pengguna yang belum punya device tidak bisa
memakai broker platform, karena ACL hanya mengenal access token device. Solusinya, berikan
setiap pengguna kredensial MQTT pribadi (dibuat acak, bisa di-reset, bukan password login) dengan
ACL `readwrite sandbox/<username>/#`. Kredensial ini dibuat oleh `mqtt_accounts`, sama seperti
akun device.

---

## 5. Relay WebSocket → TCP (jalur Relay)

### 5.1 Alur

```
Browser                    Django client (:8002)          relay (:8003)            broker
  │ POST /relay/ticket         │                              │                       │
  │  {profile, host, port, tls}│ cek login, cek alamat,       │                       │
  │───────────────────────────▶│ simpan tiket (DB, 60 dtk,    │                       │
  │◀── {"ticket": "…"} ────────│ sekali pakai)                │                       │
  │ mqtt.js connect wss://mqtt.reslab-csub.cloud/relay/<ticket>  (subprotocol "mqtt") │
  │──────────────────────────────────────────────────────────▶│                       │
  │                            │◀── POST /internal/redeem ────│ tukarkan tiket        │
  │                            │─── {user, host, port, tls} ─▶│                       │
  │ frame pertama: CONNECT ───────────────────────────────────▶│ cek: paket CONNECT?  │
  │                            │                              │ resolve DNS, cek IP   │
  │                            │                              │──── TCP / TLS ───────▶│
  │◀═══════════════ byte diteruskan dua arah apa adanya ══════╪══════════════════════▶│
```

- **Tiket.** Alamat tujuan tidak pernah dikirim langsung ke relay. Django memeriksa pengguna
  dan alamat, lalu membuat tiket acak yang berlaku 60 detik dan hanya bisa dipakai sekali.
  Tiket disimpan di database aplikasi client.
- **Penukaran tiket.** Relay tidak punya akses database. Ia menukarkan tiket lewat endpoint
  internal Django `POST http://127.0.0.1:8002/internal/relay/redeem/`, yang hanya menerima
  permintaan dari localhost dan ditandatangani dengan kunci bersama di `.env`.
- **Hanya MQTT.** Relay menunggu frame pertama dari browser dan memeriksa bahwa isinya paket
  MQTT CONNECT (byte pertama `0x10`, nama protokol `MQTT` atau `MQIsdp`). Baru setelah itu ia
  membuka koneksi ke broker. Dengan begitu relay tidak bisa dipakai sebagai terowongan TCP umum,
  misalnya untuk mengirim spam ke port 25 atau masuk ke SSH.
- **TLS** (`mqtts://`). Relay yang membuka TLS ke broker, dengan verifikasi sertifikat terhadap
  CA sistem dan SNI = nama host. Hubungan browser–relay sudah terenkripsi (`wss://`), jadi data
  terenkripsi di kedua sisi. Relay melihat byte yang lewat, termasuk password di paket CONNECT,
  tetapi tidak menyimpan atau mencatatnya.
- **Pesan error** dikirim sebagai close code WebSocket (mis. `4403 Address not allowed`,
  `4408 Broker unreachable`, `4495 TLS verification failed`) dan diterjemahkan UI menjadi
  kalimat yang jelas.

### 5.2 Pembatasan alamat (mencegah SSRF)

Tanpa pembatasan, relay bisa dipakai untuk menjangkau layanan di dalam VPS sendiri. Contohnya
Mosquitto `127.0.0.1:1883` milik bridge, MySQL, Redis, atau alamat metadata cloud
`169.254.169.254`. Aturannya:

| Aturan | Rincian |
|---|---|
| Port | bawaan hanya **1883** dan **8883**; daftar port tambahan bisa diatur di `.env` (`RELAY_ALLOWED_PORTS`, mis. 1884, 8884). Port < 1024 selain itu ditolak |
| Alamat IP | DNS di-resolve **oleh relay**. Semua hasilnya diperiksa: loopback, privat (10/8, 172.16/12, 192.168/16), link-local (169.254/16, termasuk metadata), CGNAT (100.64/10), multicast, dan yang setara di IPv6 ditolak. Koneksi dibuka ke IP yang sudah diperiksa itu, bukan dengan resolve ulang, untuk mencegah *DNS rebinding* |
| Broker platform | `iot.reslab-csub.cloud:8883` diizinkan. Walaupun alamatnya IP publik VPS sendiri, yang dipakai adalah listener TLS publik dengan ACL yang sama dengan device. `127.0.0.1:1883` tetap ditolak |
| Daftar blokir | `RELAY_DENY_HOSTS` di `.env` untuk host yang disalahgunakan |

### 5.3 Batas pemakaian

| Batas | Bawaan | Alasan |
|---|---|---|
| Koneksi relay serentak per pengguna | 5 | satu orang tidak menghabiskan sumber daya VPS |
| Koneksi relay total | 200 | VPS kecil |
| Tiket per pengguna per menit | 20 | mencegah reconnect berputar cepat |
| Laju data per koneksi | 64 KB/dtk per arah | relay bukan jalur unduhan besar |
| Ukuran frame | 256 KB | sesuai batas pesan yang wajar |
| Tanpa lalu lintas | 10 menit (PINGREQ dari mqtt.js tetap dihitung) | koneksi mati dibersihkan |
| Umur koneksi | 12 jam | tab yang terlupa tidak terbuka selamanya |

Setiap koneksi relay dicatat ke journal: waktu, pengguna, host:port, IP tujuan, durasi, jumlah
byte, dan alasan putus. **Payload tidak dicatat.**

### 5.4 Implementasi

- Layanan terpisah `mqttc-relay`: Python asyncio + pustaka `websockets`, satu proses, sekitar
  300 baris. Tidak memakai Django supaya kecil, cepat, dan mudah diaudit.
- Unit systemd dengan sandbox ketat: user sendiri, tanpa akses tulis ke disk, `MemoryMax`,
  `IPAddressDeny=` untuk jaringan privat dan link-local (lapisan pengaman kedua di level kernel).
  Loopback tetap diizinkan (`IPAddressAllow=127.0.0.1`) karena relay perlu menghubungi
  `127.0.0.1:8002`. Systemd tidak bisa membatasi per port, jadi larangan ke
  `127.0.0.1` port lain tetap dijaga oleh pemeriksaan alamat di kode relay.
- Nginx `location /relay/` → `127.0.0.1:8003` dengan header Upgrade, `limit_conn` per IP.

---

## 6. Model data aplikasi client

Pesan MQTT **tidak** disimpan di server; pesan hanya ada di memori browser. Yang disimpan:

| Model | Isi |
|---|---|
| `User` | `sub` OIDC, username, email, nama (disalin dari platform setiap login) |
| `ConnectionProfile` | owner, name, scheme (`mqtt`/`mqtts`/`ws`/`wss`), host, port, path, client_id_prefix, username, protocol_version, keepalive, clean_start, will_topic/payload/qos/retain, `ca_pem` (L), `platform_device_id` (bila dari device), urutan, warna |
| `SubscriptionPreset` | profile, topic_filter, qos, color, muted |
| `SavedMessage` | owner, profile (opsional), name, topic, payload, format, qos, retain |
| `RelayTicket` | token (hash), user, host, port, tls, `ca_pem`, dibuat, dipakai (untuk sekali pakai); dihapus berkala |
| `UserSettings` | tema, batas pesan, format waktu |

Password broker tidak punya kolom di database. Profil dari device platform juga tidak menyimpan
token: token diambil ulang dari API setiap kali connect, sehingga token yang di-*regenerate* di
platform otomatis berlaku.

---

## 7. Teknologi

| Bagian | Pilihan | Alasan |
|---|---|---|
| Backend | Django 5.2 + template + Bootstrap 5.3 | sama dengan platform, mudah dipelajari mahasiswa |
| MQTT di browser | mqtt.js 5.x, disalin ke `static/` (tanpa CDN) | pustaka MQTT-over-WebSocket paling matang, mendukung MQTT 5; dipakai untuk kedua jalur |
| Relay | Python asyncio + `websockets`, layanan terpisah | penerus byte kecil tanpa Django |
| JavaScript | modul ES biasa (tanpa build step) | konsisten dengan `json_viewer.js`/`json_editor.js` |
| Login | `mozilla-django-oidc` (client), `django-oauth-toolkit` (platform) | standar OIDC, terpelihara baik |
| Database | MySQL yang sudah ada, **database dan user MySQL terpisah** (`mqttc`) | tidak berbagi tabel dengan platform; backup bisa digabung |
| Web server | Gunicorn (WSGI) di `127.0.0.1:8002` | halaman client tidak butuh WebSocket di sisi Django |
| Repo | repo terpisah `mqtt_client` (repo ini) | siklus rilis sendiri; platform hanya diubah di bagian 3–4 |

---

## 8. Deploy di VPS yang sama

### 8.1 Pembagian di server

| Bagian | Platform (sudah ada) | MQTT client (baru) |
|---|---|---|
| Domain | `iot.reslab-csub.cloud` | `mqtt.reslab-csub.cloud` (record A/AAAA ke IP VPS yang sama) |
| User Linux | `iot` | `mqttc` (terpisah; tidak bisa membaca `/srv/iot`) |
| Folder | `/srv/iot` | `/srv/mqttc` |
| Proses | Daphne `127.0.0.1:8001`, Mosquitto, worker | Gunicorn `127.0.0.1:8002`, relay `127.0.0.1:8003` |
| Unit systemd | `iot.target` (iot-web, iot-mqtt, …) | `mqttc.target` (`mqttc-web`, `mqttc-relay`, `mqttc-cleanup.timer`) |
| Database | `iot` | `mqttc`, user MySQL sendiri tanpa hak ke database `iot` |
| Nginx | `sites-available/iot-platform` | `sites-available/mqtt-client` |
| Sertifikat | `iot.reslab-csub.cloud` | sertifikat sendiri lewat webroot yang sama (`certbot certonly --webroot -w /var/www/certbot -d mqtt.reslab-csub.cloud`) |
| Backup | `iot-backup.timer` | database `mqttc` ditambahkan ke skrip backup |

Kedua aplikasi tidak saling berbagi file atau database. Satu-satunya hubungan adalah lewat HTTPS
publik (OIDC dan API) dan broker MQTT. Dengan begitu, kebocoran di aplikasi client tidak membuka
data platform.

### 8.2 Kebutuhan sumber daya (perkiraan)

| Proses | RAM |
|---|---|
| Gunicorn, 2 worker | ± 120 MB |
| Relay (200 koneksi) | ± 60 MB |
| Mosquitto, tambahan listener WebSocket | kecil |

VPS 2 GB yang sekarang cukup. Pantau dengan `systemctl status` dan `free -h` setelah dipakai satu
kelas.

### 8.3 Perubahan karena domain platform berubah

Domain platform kini `iot.reslab-csub.cloud`. Yang berkaitan dengan rancangan ini:

- `MQTT_PUBLIC_HOST`, `OTA_BASE_URL`, `CSRF_TRUSTED_ORIGINS`, `DJANGO_ALLOWED_HOSTS` di `.env`
  platform memakai domain baru;
- `ROOT_CA` di firmware tidak berubah (tetap ISRG Root X1), tetapi `MQTT_HOST`/`SERVER` di
  firmware harus memakai domain baru;
- redirect URI OIDC dan alamat API di aplikasi client memakai domain baru;
- `docs/deploy-lightsail.md` (repo platform) masih memakai contoh `iot.contoh.my.id`, jadi tidak perlu diubah.

---

## 9. Keamanan

- **HTTPS saja.** Halaman `https://` hanya boleh membuka `wss://` (aturan *mixed content*
  browser). Broker `ws://` tanpa TLS hanya bisa dipakai saat aplikasi dijalankan lokal; di
  produksi aplikasi menyarankan memakai `mqtt://` lewat relay (yang terhubung dengan `wss://`).
- **Content-Security-Policy:** `script-src 'self'`, `connect-src 'self' wss:`. Payload pesan
  selalu ditampilkan sebagai teks (`textContent`), tidak pernah sebagai HTML, untuk mencegah
  XSS dari pesan broker.
- **Relay:** tiket sekali pakai, hanya paket MQTT, pembatasan alamat dan port, batas koneksi dan
  laju, sandbox systemd (bagian 5).
- **Password broker:** bawaan tidak disimpan. *Remember in this browser* menyimpannya di
  `localStorage` dengan peringatan bahwa siapa pun yang memakai browser itu bisa membacanya.
- **Access token device:** hanya lewat scope `devices:read` yang disetujui pengguna; ditampilkan
  tersamar (`abcd…wxyz`) dengan tombol *Show*; tidak masuk log.
- **OIDC:** Authorization Code + PKCE, `state` dan `nonce`; access token berumur pendek (10 menit)
  dan refresh token bisa dicabut; logout mencabut refresh token.
- **Dua subdomain satu situs.** `iot.` dan `mqtt.reslab-csub.cloud` dianggap *same-site* oleh
  browser, sehingga `SameSite=Lax` tidak melindungi dari permintaan antar-subdomain. Proteksi
  CSRF Django (token + pemeriksaan Origin) tetap berlaku di kedua aplikasi. Cookie dibiarkan
  *host-only*, dan nama cookie dibedakan (`mqttc_sessionid`, `mqttc_csrftoken`).
- **Broker platform:** batas koneksi per IP di Nginx, `max_connections` di Mosquitto, ACL sama
  dengan device.
- **Django:** `check --deploy` bersih, rate limit login seperti platform, CSRF untuk semua form.

---

## 10. Tahapan pengerjaan

| Tahap | Isi | Hasil yang bisa dicoba |
|---|---|---|
| **M0** Broker WebSocket | listener `9001` + `location /mqtt` di Nginx, alamat `wss` di tab MQTT halaman device, panduan deploy | `mosquitto_sub` dan halaman uji mqtt.js tersambung ke `wss://iot.reslab-csub.cloud/mqtt` dengan token device |
| **M1** Platform sebagai penyedia OIDC | app `oauth` (django-oauth-toolkit), consent, `next=` di Sign up, API `/api/v2/me[/devices]`, *Connected apps*; tes | login dari klien uji OIDC |
| **M2** Kerangka aplikasi client | project Django baru, login OIDC, layout, tema, model profil + CRUD | login dan mengelola profil koneksi |
| **M3** MVP MQTT (Direct) | connect/disconnect multi-koneksi, subscribe, daftar pesan, publish, riwayat, *Saved messages*, profil dari device platform | uji device sungguhan dan tiruan lewat `wss://` |
| **M4** Relay TCP | tiket, endpoint redeem, layanan `mqttc-relay`, pembatasan alamat/port/laju, close code + pesan error, profil `mqtt://`/`mqtts://` | tersambung ke `mqtts://iot.reslab-csub.cloud:8883` dan `mqtt://broker.hivemq.com:1883`; `mqtt://127.0.0.1:1883` ditolak |
| **M5** Alat uji platform (L) | simulator device, auto-responder command, simulasi OTA, sandbox per pengguna | menguji aturan dan dashboard tanpa ESP32 |
| **M6** Kenyamanan (L) | topic tree, grafik kecil, placeholder dinamis, publish berulang, opsi MQTT 5, CA sendiri/mTLS, ekspor | — |
| **M7** Deploy | DNS `mqtt.reslab-csub.cloud`, sertifikat, user dan database `mqttc`, systemd, backup, panduan | aplikasi publik |

M0 dan M1 mengubah platform. M2 dan seterusnya dikerjakan di repo aplikasi client. M4 dibuat
setelah M3 supaya jalur Direct, yang lebih sederhana, sudah teruji lebih dulu. Setiap tahap
mendapat dokumen di `docs/` masing-masing repo, seperti tahap platform.

---

## 11. Risiko dan keterbatasan

| Hal | Dampak | Penanganan |
|---|---|---|
| Relay = VPS membuka koneksi keluar atas permintaan pengguna | bisa disalahgunakan untuk menyerang broker lain atas nama IP VPS | hanya pengguna login, hanya paket MQTT, batas koneksi/laju, log per koneksi, `RELAY_DENY_HOSTS`; akun penyalah guna bisa dinonaktifkan di platform |
| SSRF ke layanan internal | akses ke Mosquitto bridge, MySQL, Redis, metadata | pembatasan IP setelah resolve + `IPAddressDeny` systemd (bagian 5.2) |
| Relay melihat byte yang lewat | secara teori bisa membaca password broker dan pesan | relay tidak mencatat payload; kodenya kecil dan terbuka untuk diaudit; untuk broker platform sarankan jalur Direct |
| Koneksi hidup selama tab terbuka | simulator berhenti bila tab ditutup atau laptop tidur | dijelaskan di UI; untuk simulasi jangka panjang tetap pakai `simulate_devices`/`fake_mqtt_device.py` |
| Satu VPS untuk platform, broker, dan client | beban client (relay) bisa mengganggu platform | batas koneksi total, `MemoryMax`/`CPUQuota` di unit `mqttc-*`; pindahkan client ke VPS lain bila pengguna banyak |
| Mosquitto tidak membatasi laju pesan per klien | satu klien bisa membanjiri topik device-nya sendiri | batas di sisi UI dan laju relay; pertimbangkan EMQX bila pengguna banyak |
| Broker yang membatasi IP (allowlist) | lewat relay, yang terlihat adalah IP VPS | dijelaskan di UI |
| Token device ikut terbaca aplikasi client | bila aplikasi client bocor, token device bocor | scope eksplisit + consent, token tidak disimpan di DB client, bisa *Revoke* di platform |
| Banyak pesan per detik | browser lambat | batas pesan di memori, render bertahap (`requestAnimationFrame`) |

---

## 12. Pengujian

- **Platform:** tes alur OAuth (authorize → token → API), scope (`devices:read` wajib untuk
  `/api/v2/me/devices`), API hanya mengembalikan `visible_devices`, akun nonaktif ditolak.
- **Client (Django):** tes login (mock OIDC), CRUD profil, pengguna hanya melihat profilnya
  sendiri, password tidak pernah tersimpan, tiket relay (kedaluwarsa, sekali pakai, milik
  pengguna lain ditolak, rate limit).
- **Relay (pytest + asyncio):**
  - paket bukan CONNECT ditolak;
  - pembatasan alamat: `127.0.0.1`, `10.x`, `169.254.169.254`, `::1`, nama host yang resolve ke
    IP privat, dan port di luar daftar semuanya ditolak;
  - DNS rebinding: koneksi memakai IP hasil pemeriksaan;
  - batas koneksi per pengguna, batas laju, timeout;
  - TLS: sertifikat sah diterima, self-signed ditolak tanpa CA sendiri.
- **End-to-end:** Playwright + Mosquitto lokal (listener TCP dan WebSocket): connect lewat kedua
  jalur, subscribe, publish, retain, reconnect, penolakan ACL, simulator.
- **Uji bersama platform:** simulator mengirim telemetri → dashboard platform berubah → aturan
  ECA menyala → command sampai di auto-responder → status command SUCCEEDED.

---

## 13. Yang masih perlu diputuskan

1. **Profil koneksi**: disimpan di server (bisa dipakai dari laptop mana pun, tanpa password)
   atau hanya di browser? Rancangan ini memakai penyimpanan di server.
2. **Sandbox per pengguna** (bagian 4): perlu sejak MVP untuk mahasiswa yang belum punya
   device, atau cukup di tahap lanjutan?
3. **Port relay tambahan** selain 1883/8883 (mis. broker kampus di port lain)?
