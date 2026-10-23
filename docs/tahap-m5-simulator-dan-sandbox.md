# Tahap M5: Sandbox, simulator device, auto-responder, simulasi OTA

Tahap ini membuat aplikasi bisa dipakai **tanpa perangkat keras**:

- **MQTT sandbox**: akun MQTT pribadi di broker IoT Platform, tanpa perlu device;
- **publish berulang** dan **placeholder** (`{{counter}}`, `{{random:20:30}}`, …);
- **bersikap seperti device**: kirim telemetri tiruan, jawab command otomatis, laporkan
  desired state, dan menjalani pembaruan firmware (OTA) tiruan.

Pasangannya di platform: **tahap 23** (`IoT_platform/docs/tahap-23-mqtt-sandbox.md`).

## 1. MQTT sandbox

Mahasiswa sering belum punya device, tetapi ingin mencoba broker platform. Device virtual bisa
dibuat, tetapi topiknya terbatas pada topik device. Sandbox memberi ruang topik bebas:

| | Device | Sandbox |
|---|---|---|
| Username / password | access token device | `sbx-<id>` / password acak |
| Topik | `<prefix>/<token>/telemetry`, `…/desired`, … | `sandbox/<username>/#` (milik sendiri) dan `sandbox/public/#` (bersama) |
| Data masuk ke dashboard platform | ya | tidak (hanya MQTT) |
| Dibuat di | halaman Devices platform | profil platform → kartu *MQTT sandbox* |

Alurnya:

```
IoT Platform: Profile → MQTT sandbox → Create          (akun sbx-5, topik sandbox/rina/#)
     │  mqtt_accounts (timer 2 menit) menulis password + ACL Mosquitto
     ▼
MQTT Client: Connections → From IoT Platform → MQTT sandbox → Create connection
     │  saat Connect: GET /api/v2/me/sandbox (scope mqtt:sandbox) → username + password
     ▼
mqtt.js ══ wss://iot.reslab-csub.cloud/mqtt ══▶ Mosquitto (user sbx-5)
```

Password sandbox **tidak disimpan** di aplikasi ini. Profil hanya bertanda `platform_sandbox`;
password diambil dari API setiap kali Connect. Bila password di-*reset* di platform, profil tetap
jalan (setelah timer platform menulis ulang file password, paling lama ±2 menit).

Topik langganan di profil boleh memakai `{sandbox}`, yang diganti dengan `sandbox/<username>`
saat Connect. Profil sandbox baru berlangganan `{sandbox}/#`.

### Izin baru (scope `mqtt:sandbox`)

`OIDC_SCOPES` bawaan sekarang `openid profile email devices:read mqtt:sandbox`. Pengguna yang
sudah login sebelum tahap ini masih memegang token lama tanpa scope itu. Halaman *From IoT
Platform* lalu menampilkan **Sign in again to allow**: logout, login lagi, dan platform
menanyakan izin baru (*Use your MQTT sandbox account…*).

| Jawaban API sandbox | Tampilan di client |
|---|---|
| 403 (scope belum disetujui) | *Sign in again to allow* |
| `enabled: false` | *Create sandbox account on IoT Platform ↗* |
| `enabled: true` | *Create connection* / *Open connection* |
| `available: false` (fitur sandbox dimatikan di platform) | kartu tidak tampil |

## 2. Publish berulang dan placeholder

Kartu **Automation** di halaman koneksi: *Publish the message above every N s → Start*. Pesan di
kotak Publish dikirim berulang (minimal 1 detik) sampai *Stop*, koneksi putus, atau halaman
ditutup. Bila koneksi sedang tersambung ulang, pengiriman menunggu.

Placeholder diganti **setiap kali** pesan dikirim, di topik maupun payload:

| Placeholder | Contoh hasil |
|---|---|
| `{{counter}}` | 1, 2, 3, … (nomor pesan sejak halaman dibuka) |
| `{{timestamp}}` | `2026-10-22T07:57:40.302Z` |
| `{{unix}}` | `1792655860` |
| `{{random:20:30}}` | `27.86` (2 desimal) |
| `{{int:0:100}}` | `42` |
| `{{bool}}` | `true` / `false` |

Contoh: `{"temperature": {{random:20:30}}, "n": {{counter}}}`. Pemeriksaan JSON di bawah payload
memeriksa hasil penggantiannya, jadi `{{random:20:30}}` tanpa tanda kutip dianggap angka yang sah.

## 3. Bersikap seperti device

Bagian *Behave like the device* hanya muncul pada profil **device platform** (bukan sandbox atau
broker lain), karena memerlukan topik device dari API.

| Pilihan | Yang dilakukan | Topik |
|---|---|---|
| Simulate sensors | mengisi kotak Publish dengan topik telemetri dan payload dari **variabel device** di platform (`{{random:min:max}}` sesuai batas, bawaan 0–100; `{{int:0:1}}` untuk boolean; aktuator dilewati); tekan Start untuk mengirim berulang | `…/telemetry` |
| Answer commands automatically | setiap command masuk dijawab dengan templat (bawaan `{"success": true, "method": "{{method}}"}`; juga `{{id}}`) | `…/commands/<id>/response` |
| Report desired states back as telemetry | desired `{"lamp": 1}` diterima → dikirim kembali sebagai telemetri, seperti device yang menjalankan perintah lalu melapor | `…/telemetry` |
| Simulate firmware updates (OTA) | command `ota` dijawab, lalu laporan progres dikirim seperti firmware ESP32 (`firmware/esp32_mqtt`): `DOWNLOADING` 0–100 % → `DOWNLOADED` → `VERIFIED` → `UPDATING` → versi baru. Pilihan *Fail* berhenti di 50 % dengan `FAILED` | `…/firmware` |

Dengan ini satu alur lengkap bisa dicoba tanpa ESP32: buat pembaruan firmware di halaman OTA
platform, lihat command `ota` masuk di client, lalu amati status pembaruan di platform berjalan
sampai selesai (atau gagal).

Jawaban otomatis tidak masuk ke *History* publish, tetapi tetap tampil di daftar pesan (panah ↑).

## 4. Berkas yang berubah

| Berkas | Isi |
|---|---|
| `connections/models.py`, migrasi `0003` | `ConnectionProfile.platform_sandbox`, `from_platform` |
| `connections/platform_devices.py` | `load_sandbox()`, `sandbox_create` (`POST /connections/platform/sandbox/`) |
| `connections/session.py` | Connect untuk profil sandbox; `device` (nama, board, firmware, variabel) dan `sandbox` di bahan connect |
| `connections/templates/connections/platform_devices.html` | kartu MQTT sandbox |
| `connections/templates/connections/session.html` | kartu Automation |
| `static/js/session.js` | `expand()` (placeholder), publish berulang, simulator, `automate()`, `simulateOta()` |
| `accounts/platform.py` | `PlatformForbidden` (HTTP 403 = scope belum disetujui) |
| `config/settings.py` | `OIDC_SCOPES` + `mqtt:sandbox` |
| `connections/tests_m56.py` | tes sandbox dan halaman |

## 5. Mencoba di laptop

1. Platform (tahap 23): `python manage.py migrate`, pastikan `MQTT_DEVICE_LOGIN=True` (atau
   `MQTT_SANDBOX_ENABLED=True`), buka **Profile → MQTT sandbox → Create**.
2. Mosquitto lokal memakai file password/ACL dari `python manage.py mqtt_accounts` (tahap 18).
3. Client: logout lalu login lagi (izin baru), **Connections → From IoT Platform → MQTT sandbox →
   Create connection → Connect**. Tombol *Sandbox topics* (My topic, Sensor, Shared chat) mengisi
   kotak Publish.
4. Untuk device: buat koneksi device, centang pilihan otomatis, lalu kirim command dari platform.
