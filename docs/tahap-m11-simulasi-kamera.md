# Tahap M11 — Simulasi kamera ESP32-CAM

Rencana: [rencana-tahap-m11-simulasi-kamera.md](rencana-tahap-m11-simulasi-kamera.md). Pasangan dari
`IoT_platform/docs/tahap-27a-snapshot-esp32cam.md`. M11a, M11b, dan M11c dikerjakan sekaligus.

Halaman koneksi **device IoT Platform** kini bisa bersikap seperti ESP32-CAM (template
`firmware/esp32cam_mqtt` di platform), sehingga *Capture now*, snapshot berkala, aksi aturan
*Capture snapshot* (alarm + Telegram), galeri, dashboard, retensi, dan kuota bisa dicoba tanpa
perangkat.

## Pemakaian

Kartu **Automation → Behave like the device → Simulate a camera (ESP32-CAM)**:

- tercentang otomatis saat Connect bila board device di platform `esp32cam`;
- **Source**:

  | Source | Isi gambar |
  |---|---|
  | Test pattern (bawaan) | jam, nama device, sumber/nomor command, kotak-kotak dan pita warna |
  | Image files | gambar pilihan pengguna, bergiliran (tetap di browser) |
  | Webcam | kamera laptop; perlu HTTPS atau localhost dan izin browser, mati saat pilihan lain dipilih |

- **Fault**:

  | Fault | Akibat |
  |---|---|
  | No fault | normal |
  | Camera error | tidak mengunggah, jawab `success: false` |
  | Not a JPEG | unggah PNG → 415 |
  | Too large | JPEG ditambah byte kosong sampai 600 KB → 413 bila batas platform 512 KB |
  | No answer | gambar diunggah, command tidak dijawab → Expired di platform |

- **Every N s** = `snapshot_interval` (0 = hanya atas permintaan, minimal 2 s); juga diisi lewat desired.
- **Capture & upload now** = gambar dengan `X-Source: device`.
- Pratinjau gambar terakhir, baris hasil (ukuran → status HTTP, nomor snapshot), 4 hasil sebelumnya, dan
  tautan *Snapshots on IoT Platform ↗* (galeri device).

Perilaku yang ditiru dari firmware:

| Masuk | Yang dilakukan |
|---|---|
| command `capture` | (kedaluwarsa → diabaikan, M10) → jeda 0,3–1 s → unggah `X-Source: command`, `X-Command-Id` → jawab `{"success": true, "snapshot": <id>, "size": <byte>}`, atau `{"success": false, "error": "Upload failed: HTTP 413 …"}`. Command ganda (QoS 1) dipotret sekali. |
| desired `snapshot_interval`, `framesize` (1–13, ukuran esp32-camera), `quality` (10–63 → kualitas JPEG 0,95–0,30), `flash` | dipakai untuk gambar berikutnya. Bila *Report desired states* mati, simulator melaporkan kunci kamera itu sebagai telemetri (seperti firmware); bila hidup, seluruh desired sudah dilaporkan. |

Bila gambar lebih besar dari 500 KB, kualitas diturunkan otomatis (kecuali Fault *Too large*).

## Jalur unggahan

```
camera_sim.js ──POST /connections/<pk>/snapshot/ (image/jpeg, X-Source, X-Command-Id)──▶ connections/snapshot.py
                                                    ──POST <snapshot_url>──▶ IoT Platform /api/v1/<token>/snapshot
```

- Hanya profil device platform milik pengguna (400 untuk profil lain, 404 milik orang lain).
- `snapshot_url` dari `/api/v2/me/devices` (platform baru), atau `PLATFORM_URL/api/v1/<token>/snapshot`
  (platform lama); disimpan di cache server 5 menit per (pengguna, profil). Platform menjawab 401
  (token diganti) → alamat dilupakan.
- Batas aplikasi ini: `SNAPSHOT_PROXY_MAX_KB` (1024) per gambar dan `SNAPSHOT_PROXY_PER_MINUTE` (30) per
  pengguna; `Content-Type` harus `image/*`. Hanya `X-Source` dan `X-Command-Id` yang diteruskan.
- Jawaban platform (201, 413, 415, 429, …) diteruskan apa adanya. Platform tidak terjangkau 503, sesi
  platform habis 401 + `signin`, Viewer / device hilang 403.

Hasil unggahan tampil di panel kamera, tidak di daftar pesan MQTT (daftar itu khusus pesan MQTT dan ikut
diekspor).

## Berkas

| Berkas | Isi |
|---|---|
| `connections/snapshot.py`, `connections/urls.py` | proxy `POST /connections/<pk>/snapshot/` |
| `connections/session.py` | `config.urls.snapshot`, `config.urls.gallery` |
| `config/settings.py`, `deploy/env.production.example` | `SNAPSHOT_PROXY_MAX_KB`, `SNAPSHOT_PROXY_PER_MINUTE` |
| `static/js/camera_sim.js` (baru) | pembuat gambar, `capture`, desired, berkala, Fault, webcam |
| `static/js/session.js` | memanggil `CameraSim` di `connect()` dan `automate()` |
| `connections/templates/connections/session.html`, `static/css/app.css` | panel kamera |
| `deploy/nginx/mqtt-client.conf` | `location ~ ^/connections/[0-9]+/snapshot/$` (`client_max_body_size 1m`), `Permissions-Policy: camera=(self)` |
| `connections/tests_m11.py` | 8 tes proxy dan halaman |
| IoT_platform `api/v2.py` | `snapshot_url` per device (Editor ke atas) |

## Pengujian

- `python manage.py test connections` (tes proxy: penerusan dan header, `snapshot_url`, galat platform,
  batas ukuran/tipe/laju, profil salah, sesi/akses, token diganti, halaman).
- `camera_sim.js` diuji di Chromium dengan `fetch` tiruan:
  - command dijawab, command ganda diabaikan;
  - desired `framesize`/`quality`/`flash`/`snapshot_interval` dipakai dan dilaporkan;
  - snapshot berkala;
  - keempat Fault;
  - webcam (perangkat tiruan Chromium) dan file gambar.

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh      # collectstatic, restart
sudo cp /srv/mqttc/app/deploy/nginx/mqtt-client.conf /etc/nginx/sites-available/mqtt-client
sudo nginx -t && sudo systemctl reload nginx
```

Tidak ada migrasi. Platform perlu sudah memuat tahap 27a (endpoint snapshot); `snapshot_url` di API v2
opsional.
