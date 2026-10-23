# MQTT Client Web

Aplikasi MQTT client berbasis web untuk IoT platform (`iot.reslab-csub.cloud`), akan
di-deploy di `mqtt.reslab-csub.cloud`. Pengguna login dengan akun IoT platform, lalu bisa
menyambung ke broker MQTT mana pun:

- broker WebSocket (`wss://`) langsung dari browser;
- broker TCP (`mqtt://` 1883, `mqtts://` 8883) lewat relay di server.

Fiturnya: subscribe, publish, daftar pesan, profil koneksi, profil dari device platform dan akun
MQTT sandbox, simulator device (auto-responder, OTA tiruan), pohon topik, grafik, MQTT 5, ekspor.
Repo platform: `IoT_platform` (folder bersebelahan).

Status: **tahap M7** (semua tahap rancangan selesai; panduan pasang di server: [docs/deploy.md](docs/deploy.md)). Rancangan lengkap ada di
[docs/rencana-mqtt-client.md](docs/rencana-mqtt-client.md).

## Tahapan

| Tahap | Isi | Repo | Status |
|---|---|---|---|
| M0 | Listener WebSocket Mosquitto (`wss://iot.reslab-csub.cloud/mqtt`) | IoT_platform (tahap 21) | selesai, sudah di server |
| M1 | Platform sebagai penyedia OpenID Connect + API device | IoT_platform (tahap 22) | selesai, sudah di server |
| M2 | Kerangka aplikasi client, login, profil koneksi | mqtt_client | selesai ([docs](docs/tahap-m2-kerangka-dan-login.md)) |
| M3 | MVP MQTT (jalur Direct `wss://`) | mqtt_client | selesai ([docs](docs/tahap-m3-koneksi-mqtt.md)) |
| M4 | Relay WebSocket → TCP (`mqtt://`, `mqtts://`) | mqtt_client | selesai ([docs](docs/tahap-m4-relay.md)) |
| M5 | Sandbox, simulator device, auto-responder, simulasi OTA | mqtt_client + IoT_platform (tahap 23) | selesai ([docs](docs/tahap-m5-simulator-dan-sandbox.md)) |
| M6 | Topic tree, grafik, MQTT 5, ekspor, CA sendiri | mqtt_client | selesai ([docs](docs/tahap-m6-analisis-pesan.md)) |
| M7 | Deploy di VPS yang sama dengan platform | mqtt_client | selesai ([docs](docs/deploy.md)) |

## Menjalankan di laptop

IoT Platform berjalan di port 8000, aplikasi ini di port 9000. Langkah lengkap (termasuk
mendaftarkan aplikasi di platform): [docs/tahap-m2-kerangka-dan-login.md](docs/tahap-m2-kerangka-dan-login.md).

```bash
pip install -r requirements.txt
cp .env.example .env          # isi DB_PASSWORD, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET
python manage.py migrate
python manage.py runall       # web (127.0.0.1:9000) + relay, dari satu terminal; Ctrl+C mematikan keduanya
```

`runall` sama dengan menjalankan dua perintah ini di dua terminal:

```bash
python manage.py runserver 127.0.0.1:9000
python -m relay               # relay untuk broker mqtt:// dan mqtts:// (tahap M4)
```

Pilihan lain: `runall 127.0.0.1:9100` (port lain), `runall --only web` (tanpa relay).
`runall` memeriksa dulu `.env` relay (`RELAY_SHARED_SECRET`, port, `RELAY_REDEEM_URL`) dan
menjelaskan bila ada yang salah. Perubahan kode relay baru berlaku setelah `runall` dijalankan
ulang; web memuat ulang sendiri seperti `runserver`.

Pustaka mqtt.js disimpan di `static/vendor/mqtt.min.js` (versi 5.15.2). Untuk memperbarui:

```bash
curl -L -o static/vendor/mqtt.min.js https://cdn.jsdelivr.net/npm/mqtt@<versi>/dist/mqtt.min.js
```
