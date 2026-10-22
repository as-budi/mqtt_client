# Tahap M2: Kerangka aplikasi, login dengan IoT Platform, profil koneksi

Tahap ini membuat aplikasi MQTT Client berdiri: project Django baru, login memakai akun IoT
Platform (OpenID Connect), tampilan dasar, dan pengelolaan **profil koneksi**. Tombol
**Connect** belum berfungsi; koneksi MQTT di browser dikerjakan di tahap M3.

Prasyarat di IoT Platform: tahap 21 dan 22 (repo `IoT_platform`).

## 1. Struktur

```
mqtt_client/
├── manage.py
├── requirements.txt          Django, mysqlclient, python-dotenv, Authlib, joserfc, requests
├── .env.example
├── config/                   settings.py, urls.py, wsgi.py
├── accounts/                 pengguna dari platform, login OIDC, token platform
│   ├── models.py             User (+ platform_sub)
│   ├── oidc.py               klien OIDC (Authlib) + sync_user()
│   ├── platform.py           simpan/perbarui/cabut token, api_get()
│   ├── middleware.py         PlatformSessionMiddleware
│   └── views.py              halaman depan, /login/, /oidc/callback/, /logout/
├── connections/              profil koneksi broker
│   ├── models.py             ConnectionProfile, SubscriptionPreset
│   ├── validators.py         aturan topik MQTT (nama dan filter)
│   ├── presets.py            templat: broker platform, EMQX, HiveMQ, Mosquitto
│   ├── forms.py, views.py, urls.py, templates/
├── templates/                base.html, includes/
├── static/                   css/app.css, js/theme.js, js/connection_form.js
└── docs/
```

## 2. Login: aplikasi ini sebagai "relying party"

Di tahap 22 platform menjadi **penyedia** login. Sekarang sisi **pemakainya**:

```
Browser            MQTT Client (:9000)                      IoT Platform (:8000)
  │ "Sign in"          │                                          │
  │───────────────────▶│ /login/: Authlib membuat state, nonce,   │
  │                    │ code_verifier (disimpan di sesi)          │
  │◀── 302 ────────────│                                          │
  │──────────────────────────────── /o/authorize/?... ───────────▶│ login + persetujuan
  │◀──────────────────────────────── 302 /oidc/callback/?code&state│
  │───────────────────▶│ /oidc/callback/:                         │
  │                    │   cek state; POST /o/token/ (code + verifier + secret)
  │                    │──────────────────────────────────────────▶│
  │                    │◀── access_token, refresh_token, id_token ─│
  │                    │   periksa id_token dengan kunci publik (jwks), iss, aud, nonce
  │                    │   sync_user(klaim) -> login() -> simpan token di sesi
  │◀── 302 /connections/                                          │
```

Pustakanya **Authlib**. Cukup diberi tahu issuer platform; semua alamat lain dibaca dari
`<issuer>/.well-known/openid-configuration`. Authlib juga yang membuat PKCE (S256), state, dan
nonce, lalu memeriksa id_token.

**Pengguna lokal.** Tabel `User` aplikasi ini hanya cermin akun platform:

- dikenali dari `platform_sub` (klaim `sub` = id pengguna di platform), bukan username;
- username, nama, dan email diperbarui setiap login;
- password tidak bisa dipakai (`set_unusable_password`).

Bila username dipakai pengguna lain yang sudah berganti nama di platform, pengguna lama itu
dinamai sementara `<username>~<sub>` sampai ia login lagi.

**Cookie.** Di laptop, platform (port 8000) dan aplikasi ini (port 9000) sama-sama di
`127.0.0.1`. Browser tidak memisahkan cookie per port, jadi nama cookie dibedakan:
`mqttc_sessionid` dan `mqttc_csrftoken`. Tanpa ini, login di satu aplikasi menimpa sesi aplikasi
lainnya.

## 3. Token platform dan "sesi ikut platform"

Setelah login, token disimpan di **sesi server** (`session["platform_token"]`, tabel
`django_session`). Token tidak pernah dikirim ke JavaScript atau ditulis di cookie; cookie hanya
berisi id sesi acak.

`PlatformSessionMiddleware` berjalan di setiap request:

| Keadaan | Tindakan |
|---|---|
| access token masih berlaku | tidak ada |
| sudah (hampir) kedaluwarsa | tukar refresh token di `/o/token/`; simpan token baru (refresh token ikut berganti) |
| platform menolak (`400 invalid_grant`) | logout + pesan "Your IoT Platform session has ended" |
| platform tidak bisa dihubungi | tetap login; coba lagi paling cepat 60 detik kemudian |

Platform menolak bila pengguna mencabut izin di **Connected apps**, akunnya dinonaktifkan, atau
refresh token dipakai ulang. Karena access token berumur 10 menit, pencabutan berlaku paling
lambat sekitar 10 menit kemudian.

**Logout:**

- **Sign out**: refresh token dicabut di platform (`/o/revoke_token/`), lalu sesi aplikasi ini
  dihapus. Login di platform tetap.
- **Sign out of IoT Platform too**: seperti di atas, lalu browser dikirim ke `/o/logout/` platform
  (dengan `id_token_hint`). Platform meminta konfirmasi, lalu mengembalikan pengguna ke halaman
  depan aplikasi ini.

`platform.api_get(request, "/api/v2/me/devices")` sudah tersedia untuk tahap M3: memanggil API
platform dengan token pengguna dan memperbaruinya otomatis bila perlu.

Catatan: rencana awal menyebut token disimpan terenkripsi. Untuk saat ini token cukup disimpan di
sesi database server, tidak di browser. Enkripsi kolom sesi bisa ditambahkan saat deploy (M7)
bila diperlukan.

## 4. Profil koneksi

| Bagian | Isian |
|---|---|
| Broker | nama, warna, protokol (`wss`, `ws`, `mqtts`, `mqtt`), host, port (kosong = bawaan), path WebSocket |
| Login dan sesi | username, awalan client ID, versi MQTT (3.1.1 / 5.0), keep alive, clean start |
| Last Will | topik, payload, QoS, retain |
| Langganan tersimpan | topic filter, QoS, warna, muted (dipasang otomatis saat Connect, M3) |

Password **tidak** punya kolom. Ia akan ditanyakan saat Connect (M3).

**Jalur koneksi** ditentukan protokol:

- `wss://` / `ws://` → **Direct**: browser langsung ke broker.
- `mqtts://` / `mqtt://` → **Relay**: lewat server, tahap M4. Profilnya sudah bisa disimpan
  sekarang.

**Validasi:**

- host tanpa `wss://` atau path;
- port 1–65535;
- `ws://` ditolak di server produksi (aturan *mixed content* browser);
- topik Last Will tanpa wildcard;
- topic filter mengikuti aturan MQTT (`connections/validators.py`): `#` hanya di level
  terakhir, `+` mengisi satu level penuh;
- topic filter tidak boleh ganda dalam satu profil;
- nama profil unik per pengguna.

**Templat** (`connections/presets.py`): broker IoT Platform (`wss://<domain platform>/mqtt`),
EMQX (`broker.emqx.io:8084`), HiveMQ (`broker.hivemq.com:8884`), dan Mosquitto
(`test.mosquitto.org:8081`).

**Keamanan data:** setiap query diawali `ConnectionProfile.objects.filter(owner=request.user)`,
jadi profil milik orang lain selalu 404.

## 5. Menjalankan di laptop

```bash
# 1. IoT Platform (repo IoT_platform), port 8000. Sekali saja:
python manage.py oidc_key
python manage.py oauth_client "MQTT Client (dev)" \
       --redirect-uri http://127.0.0.1:9000/oidc/callback/ --logout-uri http://127.0.0.1:9000/
python manage.py runserver            # http://127.0.0.1:8000

# 2. MQTT Client (repo ini), terminal lain
conda create -n mqtt_client python=3.12 && conda activate mqtt_client
conda install -c conda-forge mysqlclient
pip install -r requirements.txt
cp .env.example .env                  # isi DB_PASSWORD, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET
python manage.py migrate
python manage.py runserver 127.0.0.1:9000
```

Database MySQL untuk aplikasi ini terpisah dari platform:

```sql
CREATE DATABASE mqttc CHARACTER SET utf8mb4;
CREATE USER 'mqttc_user'@'localhost' IDENTIFIED BY 'ganti_password';
GRANT ALL PRIVILEGES ON mqttc.* TO 'mqttc_user'@'localhost';
GRANT ALL PRIVILEGES ON test_mqttc.* TO 'mqttc_user'@'localhost';
```

Buka `http://127.0.0.1:9000`, lalu **Sign in with IoT Platform**. Gunakan alamat `127.0.0.1`,
bukan `localhost`: redirect URI yang didaftarkan harus sama persis.

Tes: `python manage.py test` (30 tes; platform diganti tiruan). Alur sungguhan (login → setuju →
kembali → buat profil → keluar dari kedua aplikasi) sudah dicoba dengan kedua server berjalan
berdampingan.

## 6. Berikutnya (M3)

- Tombol **Connect**: mqtt.js di browser, password ditanyakan saat itu.
- Halaman koneksi: daftar pesan, subscribe dan publish.
- Profil dari device platform lewat `api_get(request, "/api/v2/me/devices")`.
