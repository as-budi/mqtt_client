# MQTT Client Web

Aplikasi MQTT client berbasis web untuk IoT platform (`iot.reslab-csub.cloud`), akan
di-deploy di `mqtt.reslab-csub.cloud`. Pengguna login dengan akun IoT platform, lalu bisa
menyambung ke broker MQTT mana pun:

- broker WebSocket (`wss://`) langsung dari browser;
- broker TCP (`mqtt://` 1883, `mqtts://` 8883) lewat relay di server.

Fiturnya: subscribe, publish, daftar pesan, profil koneksi, dan profil dari device platform.
Repo platform: `IoT_platform` (folder bersebelahan).

Status: **tahap M2** (login dengan IoT Platform dan profil koneksi). Rancangan lengkap ada di
[docs/rencana-mqtt-client.md](docs/rencana-mqtt-client.md).

## Tahapan

| Tahap | Isi | Repo | Status |
|---|---|---|---|
| M0 | Listener WebSocket Mosquitto (`wss://iot.reslab-csub.cloud/mqtt`) | IoT_platform (tahap 21) | selesai, sudah di server |
| M1 | Platform sebagai penyedia OpenID Connect + API device | IoT_platform (tahap 22) | selesai, sudah di server |
| M2 | Kerangka aplikasi client, login, profil koneksi | mqtt_client | selesai ([docs](docs/tahap-m2-kerangka-dan-login.md)) |
| M3 | MVP MQTT (jalur Direct `wss://`) | mqtt_client | rencana |
| M4 | Relay WebSocket → TCP (`mqtt://`, `mqtts://`) | mqtt_client | rencana |
| M5 | Simulator device, auto-responder, simulasi OTA | mqtt_client | rencana |
| M6 | Topic tree, grafik, MQTT 5, ekspor | mqtt_client | rencana |
| M7 | Deploy di VPS yang sama dengan platform | keduanya | rencana |

## Menjalankan di laptop

IoT Platform berjalan di port 8000, aplikasi ini di port 9000. Langkah lengkap (termasuk
mendaftarkan aplikasi di platform): [docs/tahap-m2-kerangka-dan-login.md](docs/tahap-m2-kerangka-dan-login.md).

```bash
pip install -r requirements.txt
cp .env.example .env          # isi DB_PASSWORD, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET
python manage.py migrate
python manage.py runserver 127.0.0.1:9000
```
