# Tahap M7: Memasang MQTT Client di server (VPS yang sama dengan IoT Platform)

Panduan ini memasang MQTT Client di `https://mqtt.reslab-csub.cloud`, di VPS yang **sudah**
menjalankan IoT Platform (`https://iot.reslab-csub.cloud`, panduan
`IoT_platform/docs/deploy-vps.md`). Paket sistem (Python, MySQL, Nginx, certbot) sudah
terpasang dari panduan platform, jadi langkahnya jauh lebih pendek.

```
                         ┌──────────────────────────── VPS ─────────────────────────────┐
browser ── https ──▶ Nginx :443 ── iot.reslab-csub.cloud ──▶ Daphne :8001 (iot-web)        │
   │                    │                          /mqtt ──▶ Mosquitto WS 127.0.0.1:9001  │
   │                    └── mqtt.reslab-csub.cloud ───────▶ Gunicorn :8002 (mqttc-web)     │
   │                                         /relay/ ────▶ relay :8003 (mqttc-relay) ──┐  │
   │                                                          ▲ 127.0.0.1:8002/internal │  │
   └── wss://iot.…/mqtt (Direct)                              └──────── tiket ──────────┘  │
                                                    relay ── TCP ──▶ broker luar :1883/8883 ┘
```

| Bagian | User | Folder | Port (hanya 127.0.0.1) |
|---|---|---|---|
| IoT Platform | `iot` | `/srv/iot` | 8001, Mosquitto 1883 + 9001 |
| MQTT Client web | `mqttc` | `/srv/mqttc` | 8002 |
| MQTT Client relay | `mqttc` | `/srv/mqttc` | 8003 |

Tidak ada port baru yang dibuka di firewall: semuanya lewat 80/443.

## 0. Prasyarat di IoT Platform

1. Platform sudah sampai **tahap 23** (MQTT sandbox). Login MQTT Client meminta izin
   `mqtt:sandbox`; platform yang belum mengenal izin itu **menolak login**. Bila platform belum
   bisa diperbarui, sementara isi `OIDC_SCOPES=openid profile email devices:read` di `.env`
   client (fitur sandbox tidak tampil).
2. `MQTT_PUBLIC_WS_URL=wss://iot.reslab-csub.cloud/mqtt` dan `OIDC_ISSUER=https://iot.reslab-csub.cloud/o`
   sudah diisi di `.env` platform (tahap 21–22), dan `curl -s https://iot.reslab-csub.cloud/o/.well-known/openid-configuration`
   menampilkan JSON.

## 1. DNS

Buat **A record** `mqtt` → IP statis VPS yang sama (di pengelola DNS domain `reslab-csub.cloud`).
Tunggu sampai terlihat:

```bash
dig +short mqtt.reslab-csub.cloud     # harus sama dengan: dig +short iot.reslab-csub.cloud
```

## 2. Database MySQL

Database **sendiri**, terpisah dari database platform:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"     # password DB, simpan untuk .env
sudo mysql
```

```sql
CREATE DATABASE mqttc CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mqttc_user'@'localhost' IDENTIFIED BY 'PASSWORD-ACAK-TADI';
GRANT ALL PRIVILEGES ON mqttc.* TO 'mqttc_user'@'localhost';
EXIT;
```

## 3. User, kode, paket Python

```bash
sudo adduser --system --group --home /srv/mqttc --shell /bin/bash mqttc
sudo install -d -o mqttc -g mqttc -m 750 /srv/mqttc/backups
```

Ambil kode dengan git (deploy key read-only, sama seperti platform langkah 7.2):

```bash
sudo -u mqttc -H ssh-keygen -t ed25519 -N "" -f /srv/mqttc/.ssh/id_ed25519
sudo cat /srv/mqttc/.ssh/id_ed25519.pub          # tempel di GitHub: repo mqtt_client → Settings → Deploy keys
sudo -u mqttc -H git clone git@github.com:NAMA/mqtt_client.git /srv/mqttc/app
```

Pastikan `static/vendor/mqtt.min.js` ikut di repo (`ls -l /srv/mqttc/app/static/vendor/`).

```bash
sudo -u mqttc -H python3 -m venv /srv/mqttc/venv
sudo -u mqttc -H /srv/mqttc/venv/bin/pip install --upgrade pip
sudo -u mqttc -H /srv/mqttc/venv/bin/pip install -r /srv/mqttc/app/requirements.txt
```

## 4. Mendaftarkan MQTT Client di IoT Platform

Di server yang sama, sebagai user `iot`:

```bash
cd /srv/iot/app
sudo -u iot -H /srv/iot/venv/bin/python manage.py oauth_client "MQTT Client" \
    --redirect-uri https://mqtt.reslab-csub.cloud/oidc/callback/ \
    --logout-uri https://mqtt.reslab-csub.cloud/
```

Perintah menampilkan `client_id` dan `client_secret`. **`client_secret` hanya tampil sekali**:
salin langsung ke `.env` client (langkah 5), jangan ditempel di chat, email, atau dokumen. Bila
hilang: jalankan lagi dengan `--rotate-secret`, lalu perbarui `.env` dan restart `mqttc-web`.

Aplikasi pengembangan di laptop (`MQTT Client (dev)`, redirect ke `http://127.0.0.1:9000/…`)
adalah aplikasi **lain**; jangan dipakai di server.

## 5. File `.env`

```bash
sudo -u mqttc cp /srv/mqttc/app/deploy/env.production.example /srv/mqttc/app/.env
sudo chmod 600 /srv/mqttc/app/.env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # RELAY_SHARED_SECRET
sudo -u mqttc nano /srv/mqttc/app/.env
```

| Nama | Isi |
|---|---|
| `DJANGO_SECRET_KEY` | 50+ karakter acak (berbeda dari kunci platform) |
| `DJANGO_ALLOWED_HOSTS` | `mqtt.reslab-csub.cloud,127.0.0.1` (127.0.0.1 untuk relay) |
| `DB_PASSWORD` | dari langkah 2 |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | dari langkah 4 |
| `RELAY_SHARED_SECRET` | 32+ karakter acak |
| `RELAY_ALLOW_LOCAL` | **`False`** (sudah di contoh). Dengan `True`, pengguna bisa menyuruh relay masuk ke Mosquitto 127.0.0.1:1883 milik platform, MySQL, atau jaringan internal |
| `DJANGO_HTTPS` | tetap `False` sampai langkah 7 |

## 6. Database, file statis, layanan web

```bash
cd /srv/mqttc/app
sudo -u mqttc -H /srv/mqttc/venv/bin/python manage.py migrate
sudo -u mqttc -H /srv/mqttc/venv/bin/python manage.py collectstatic --noinput
sudo chmod 711 /srv/mqttc      # Nginx boleh MELEWATI folder ini menuju staticfiles
# sh -c: tanda * diuraikan sebagai root (folder /srv/mqttc tidak bisa dibaca user ubuntu)
sudo sh -c 'cp -v /srv/mqttc/app/deploy/systemd/mqttc* /etc/systemd/system/'
sudo systemctl daemon-reload
sudo systemctl start mqttc-web
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: mqtt.reslab-csub.cloud" http://127.0.0.1:8002/     # 200
```

Admin Django (`/admin/`) jarang diperlukan: pengguna dibuat otomatis saat login pertama dari
platform. Bila perlu, `manage.py createsuperuser` dengan username yang tidak mudah ditebak.

## 7. Nginx dan HTTPS

Konfigurasi platform sudah memuat server *default* yang menolak host tak dikenal, jadi
konfigurasi client cukup ditambahkan:

```bash
sudo cp /srv/mqttc/app/deploy/nginx/mqtt-client-http.conf /etc/nginx/sites-available/mqtt-client
sudo ln -s /etc/nginx/sites-available/mqtt-client /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
curl -s http://mqtt.reslab-csub.cloud/ ; echo     # "MQTT Client: HTTPS is not set up yet."

sudo certbot certonly --webroot -w /var/www/certbot -d mqtt.reslab-csub.cloud \
     --email email-anda@contoh.com --agree-tos --no-eff-email --dry-run
sudo certbot certonly --webroot -w /var/www/certbot -d mqtt.reslab-csub.cloud \
     --email email-anda@contoh.com --agree-tos --no-eff-email

sudo cp /srv/mqttc/app/deploy/nginx/mqtt-client.conf /etc/nginx/sites-available/mqtt-client
sudo nginx -t && sudo systemctl reload nginx

sudo -u mqttc sed -i 's/^DJANGO_HTTPS=False/DJANGO_HTTPS=True/' /srv/mqttc/app/.env
sudo -u mqttc -H /srv/mqttc/venv/bin/python /srv/mqttc/app/manage.py check --deploy    # no issues
```

Hook perpanjangan sertifikat (`/etc/letsencrypt/renewal-hooks/deploy/nginx.sh`) sudah dibuat di
panduan platform dan berlaku untuk semua sertifikat.

Konfigurasi akhir memuat:

- pengalihan `http://` → `https://`;
- header **Content-Security-Policy**: skrip hanya dari server ini dan jsDelivr, WebSocket hanya
  `wss://`, form hanya ke server ini dan IoT Platform;
- `/relay/` ke relay, dengan batas 10 koneksi bersamaan per IP;
- `/internal/` dijawab **404** (endpoint tiket relay hanya untuk relay di 127.0.0.1);
- batas laju login dan halaman.

## 8. Menjalankan semua layanan

```bash
sudo systemctl enable --now mqttc.target                 # mqttc-web + mqttc-relay
sudo systemctl enable --now mqttc-cleanup.timer mqttc-backup.timer
systemctl --no-pager status mqttc-web mqttc-relay | grep -E "●|Active:"
journalctl -u mqttc-relay -n 5 --no-pager                # "relay listening on 127.0.0.1:8003"
```

## 9. Pemeriksaan

Dari laptop:

```bash
curl -sI http://mqtt.reslab-csub.cloud/ | head -2                           # 301 -> https
curl -sI https://mqtt.reslab-csub.cloud/ | grep -iE "HTTP/|content-security|strict-transport"
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mqtt.reslab-csub.cloud/internal/relay/redeem/   # 404
```

Di browser:

| Uji | Hasil yang benar |
|---|---|
| Buka `https://mqtt.reslab-csub.cloud` → *Sign in with IoT Platform* | halaman izin platform, lalu daftar Connections |
| New connection → *IoT Platform broker* → Connect | tidak bisa tanpa akun (pakai sandbox atau device) |
| From IoT Platform → MQTT sandbox → Create connection → Connect | Connected, tombol *Sandbox topics* |
| From IoT Platform → device → Connect, publish *Telemetry* | data muncul di dashboard platform |
| New connection → *Others*: `mqtt://broker.emqx.io:1883` → Connect | Connected lewat Relay |
| New connection → `mqtt://127.0.0.1:1883` → Connect | ditolak: *may not connect to this address* |
| Profile platform → Connected apps | *MQTT Client* tercantum; *Revoke* → client meminta login lagi |

## 10. Memperbarui

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh
```

Skrip: `git pull` → `pip install` → `check --deploy` → `migrate` → `collectstatic` → restart
`mqttc.target`. Bila berkas di `deploy/systemd/` atau `deploy/nginx/` berubah (lihat catatan di
docs tahap), salin ulang lalu `sudo systemctl daemon-reload` / `sudo nginx -t && sudo systemctl reload nginx`.

Pengguna yang sedang terhubung lewat relay terputus sebentar saat restart; mqtt.js menyambung
ulang sendiri.

## 11. Backup dan pemulihan

`mqttc-backup.timer` membuat `/srv/mqttc/backups/mqttc-db-YYYYMMDD-HHMM.sql.gz` setiap hari
(14 hari). Sesi dan tiket relay tidak ikut (isinya sementara). Pemulihan:

```bash
gunzip -c /srv/mqttc/backups/mqttc-db-20261101-0240.sql.gz \
  | sudo mysql mqttc
sudo systemctl restart mqttc.target
```

Yang ada di database ini: profil koneksi, langganan, saved messages, dan akun pengguna (tanpa
password). Password broker yang dicentang *Remember here* hanya ada di browser pengguna.
Snapshot server dari penyedia VPS (panduan platform 2.5) juga mencakup MQTT Client.

## 12. Pemecahan masalah

| Gejala | Penyebab / cara periksa |
|---|---|
| Login: *invalid_scope* di halaman platform | platform belum tahap 23; perbarui platform atau kurangi `OIDC_SCOPES` (langkah 0) |
| Login: *Mismatching redirect URI* / *invalid_request* | redirect URI di langkah 4 tidak persis `https://mqtt.reslab-csub.cloud/oidc/callback/` (perhatikan `/` di akhir) |
| Login: *invalid_client* | `OIDC_CLIENT_SECRET` salah; buat baru dengan `--rotate-secret` |
| Setelah login kembali ke halaman awal dengan *Your IoT Platform session has ended* | jam server kacau (`timedatectl`), atau aplikasi di-*Revoke* di Connected apps |
| Halaman tanpa CSS | izin folder: `sudo chmod 711 /srv/mqttc`, lalu `curl -sI https://mqtt.reslab-csub.cloud/static/css/app.css` |
| Relay: semua koneksi `mqtt://` gagal dengan *ticket expired* | `RELAY_SHARED_SECRET` beda antara web dan relay (keduanya membaca `.env` yang sama, restart keduanya), atau `127.0.0.1` tidak ada di `DJANGO_ALLOWED_HOSTS`. Periksa `journalctl -u mqttc-relay -n 20` |
| Relay: *The relay is busy* | `RELAY_MAX_TOTAL` tercapai; periksa jumlah koneksi `ss -tn state established '( sport = :8003 )' \| wc -l` |
| Relay: broker platform `mqtts://iot.reslab-csub.cloud:8883` *could not be reached* | VPS tidak bisa menyambung ke IP publiknya sendiri; untuk broker platform pakai jalur Direct (`wss://…/mqtt`, templat *IoT Platform broker*) |
| *IoT Platform broker* tidak ada di templat | `PLATFORM_MQTT_WS_URL` kosong dan `PLATFORM_URL` bukan https |
| Sandbox: *Sign in again to allow* terus muncul | platform belum tahap 23, atau `OIDC_SCOPES` di `.env` client tanpa `mqtt:sandbox` |
| Sandbox: Connect ditolak *Not authorized* tepat setelah dibuat | akun baru ditulis ke Mosquitto oleh timer platform tiap 2 menit; tunggu sebentar |

Log: `journalctl -u mqttc-web -f`, `journalctl -u mqttc-relay -f`, `sudo tail -f /var/log/nginx/error.log`.

## 13. Daftar periksa keamanan

- [ ] `.env` izin 600, milik `mqttc`; `DJANGO_DEBUG=False`; `DJANGO_HTTPS=True`.
- [ ] `RELAY_ALLOW_LOCAL=False`; `RELAY_ORIGINS=https://mqtt.reslab-csub.cloud`.
- [ ] `curl … /internal/relay/redeem/` dari luar menjawab 404.
- [ ] `mqtt://127.0.0.1:1883` dan `mqtt://10.0.0.1:1883` ditolak relay.
- [ ] `client_secret` tidak tersimpan di mana pun selain `.env` server.
- [ ] Tidak ada akun contoh/demo; `manage.py check --deploy` bersih.
