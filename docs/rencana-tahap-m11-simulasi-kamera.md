# Rencana tahap M11: Simulasi kamera (capture snapshot)

Status: **selesai** (M11a–M11c), lihat [tahap-m11-simulasi-kamera.md](tahap-m11-simulasi-kamera.md). Pasangan dari `IoT_platform/docs/tahap-27a-snapshot-esp32cam.md`.

Tujuan: halaman koneksi device bisa **bersikap seperti ESP32-CAM**, sehingga seluruh alur kamera di
platform dapat dicoba tanpa perangkat keras:

- tombol *Capture now* di halaman device;
- snapshot berkala (`snapshot_interval`);
- aksi aturan *Capture snapshot*, termasuk tautan ke alarm dan foto ke Telegram;
- galeri, kartu dashboard, retensi, dan kuota.

## 1. Perilaku yang ditiru

Patokannya template `firmware/esp32cam_mqtt/esp32cam_mqtt.ino` di platform:

| Kejadian di ESP32-CAM | Yang dilakukan simulator |
|---|---|
| Command `capture` masuk (`…/commands/<id>`) | lewati bila kedaluwarsa (M10) → "memotret" → unggah dengan `X-Command-Id: <id>`, `X-Source: command` → jawab `{"success": true, "snapshot": <id gambar>, "size": <byte>}` di `…/commands/<id>/response` |
| Gagal memotret/mengunggah | jawab `{"success": false, "error": "<alasan>"}` |
| Desired `snapshot_interval` (detik, 0 = mati) | timer unggahan berkala dengan `X-Source: periodic` |
| Desired `framesize`, `quality`, `flash`, `lamp` | dipakai saat membuat gambar (`framesize` → ukuran, `quality` → kompresi, `flash` → gambar lebih terang) dan dilaporkan balik sebagai telemetri, seperti *Report desired states* |

Gambar **tidak** dikirim lewat MQTT. Broker platform membatasi pesan 64 KB, dan platform hanya
menerima gambar di `POST /api/v1/<token>/snapshot`. MQTT hanya membawa command dan pengaturan,
sama seperti firmware.

## 2. Jalur unggahan: lewat server mqtt_client (proxy)

```
browser (session.js)                     server mqtt_client                     IoT Platform
  canvas → JPEG ──POST /connections/<pk>/snapshot/──▶ token device dari API ──POST /api/v1/<token>/snapshot──▶ simpan
           ◀──────────── status + JSON platform (201/413/415/429/…) ────────────────────────────────────────────┘
```

Alasan memakai proxy, bukan unggah langsung dari browser:

| Pilihan | Masalah |
|---|---|
| Browser → platform langsung | beda origin (`mqtt.` vs `iot.`): perlu CORS dan *preflight* di endpoint device platform (header `X-Command-Id`, `Content-Type: image/jpeg`). Membuka CORS di API device juga melonggarkan endpoint yang dipakai perangkat sungguhan. |
| **Browser → mqtt_client → platform** (dipilih) | tidak perlu perubahan CORS. Server yang meminta token device ke `/api/v2/me/devices`, sama seperti saat Connect, dan menegakkan batas ukuran serta laju. |

Endpoint baru `POST /connections/<pk>/snapshot/`:

- login + CSRF, profil harus milik pengguna dan berupa **device platform** (`platform_device_id`);
- body JPEG maks. 1 MB; header `X-Command-Id` (angka) dan `X-Source` (`command` / `periodic` / `device`)
  diteruskan, header lain tidak;
- token device diambil dengan `platform_device()`. Supaya tidak memanggil API pada setiap gambar
  berkala, hasilnya disimpan di sesi server ±5 menit;
- jawaban platform diteruskan apa adanya (status dan JSON), supaya galat 413/415/429 terlihat di
  halaman. Galat lain:

  | Kondisi | Status |
  |---|---|
  | platform tidak terjangkau | 503 |
  | sesi platform berakhir | 401 + tautan login |
  | tidak punya akses Editor ke device | 403 |

- batas laju per pengguna, mis. 30 unggahan per menit (tabel ringan atau cache), selain batas di platform.

URL unggahan: `PLATFORM_URL + "/api/v1/<token>/snapshot"`. Opsional di platform: API
`/api/v2/me/devices` menambah `"snapshot_url"` per device, supaya client tidak perlu menebak jalurnya
bila suatu saat berubah.

## 3. Sumber gambar

Dibuat di browser dengan `<canvas>` → `canvas.toBlob(…, "image/jpeg", q)`:

| Sumber | Isi | Catatan |
|---|---|---|
| **Test pattern** (bawaan) | latar warna, kotak-kotak, nama device, jam, nomor urut, `command #id`, tulisan "SIMULATED" | tanpa izin apa pun; cocok untuk demo |
| **Image files** | gambar yang dipilih pengguna (bisa beberapa), dipakai bergiliran dan diperkecil sesuai `framesize` | file tetap di browser, tidak disimpan di server mqtt_client |
| **Webcam** | bingkai dari kamera laptop (`getUserMedia`) | perlu izin browser dan HTTPS; nyala hanya selama simulator kamera aktif. Perlu mengubah header nginx `Permissions-Policy: camera=(self)`. |

Pemetaan pengaturan:

| Desired | Pemetaan di simulator |
|---|---|
| `framesize` | QVGA 320×240 (5), VGA 640×480 (8, bawaan), SVGA 800×600 (9), UXGA 1600×1200 (10), dst. sesuai `esp32-camera` |
| `quality` | 10…63 → kualitas JPEG 0,95…0,30. Bila hasilnya melebihi batas platform (512 KB), kualitas diturunkan otomatis; pilihan *Fault* bisa sengaja melewatkannya. |

Waktu "memotret" diberi jeda acak 0,3–1,0 s supaya urutan pesan mirip perangkat sungguhan.

## 4. Antarmuka (kartu Automation → *Behave like the device*)

```
[x] Simulate camera (ESP32-CAM)      Source: [Test pattern ▾]   [Choose images…]   Fault: [None ▾]
    Periodic: every [ 0 ] s (from desired snapshot_interval)    [Capture & upload now]
    ┌─────────────┐  Last: 14:05:22 · command #42 · 640×480 · 38 KB → 201 snapshot #118
    │  preview    │  Open gallery on IoT Platform ↗
    └─────────────┘
```

- Hanya pada profil device platform. Dicentang otomatis bila board device `esp32cam`.
- Saat tercentang, command `capture` ditangani simulator kamera, bukan *Answer commands
  automatically*, sama seperti `ota` ditangani *Simulate firmware updates*.
- *Capture & upload now* = foto `X-Source: device` (seperti tombol di perangkat).
- Pilihan **Fault**, untuk menguji penanganan galat di platform:

  | Fault | Akibat |
  |---|---|
  | None | normal |
  | Camera error | tidak mengunggah, jawab `success: false` |
  | Not a JPEG | unggah PNG → 415 |
  | Too large | lewati batas ukuran → 413 |
  | No answer | unggah tetapi tidak menjawab command, sehingga command menjadi *Expired* di platform |

- Pratinjau memakai URL `data:` (CSP `img-src 'self' data:` sudah mengizinkan). Unggahan dan jawabannya
  tampil di daftar pesan sebagai baris catatan "HTTP ↑ snapshot", bukan pesan MQTT.
- Tautan galeri: `PLATFORM_URL/cameras/devices/<platform_device_id>/`.

## 5. Perubahan berkas

| Berkas | Isi |
|---|---|
| `connections/snapshot.py` (baru) | view proxy, cache token di sesi, batas ukuran/laju |
| `connections/urls.py` | `<pk>/snapshot/` |
| `connections/session.py` | `config.urls.snapshot`, `config.platformUrl` (galeri), `device.board` sudah ada |
| `connections/templates/connections/session.html` | blok *Simulate camera* |
| `static/js/session.js` (atau `static/js/camera_sim.js` baru, karena session.js sudah 1.200 baris) | pembuat gambar (test pattern / file / webcam), `handleCapture()`, timer berkala, Fault, pratinjau |
| `deploy/nginx/mqtt-client.conf` | `location = /connections/<pk>/snapshot/` dengan `client_max_body_size 1m` (bawaan server 256k); `Permissions-Policy camera=(self)` bila sumber webcam dipakai |
| `connections/tests_m11.py` | tes proxy dan halaman |
| `docs/tahap-m11-simulasi-kamera.md`, `README.md` | dokumentasi |
| (opsional, IoT_platform) `api/v2.py` | `snapshot_url` per device |

## 6. Tahapan pengerjaan

1. **M11a — capture dasar**: proxy + test pattern + command `capture` + jawaban + pratinjau. Ini sudah
   cukup untuk *Capture now* dan aksi aturan (alarm + Telegram).
2. **M11b — perilaku lengkap**: `snapshot_interval` berkala, `framesize`/`quality`/`flash`, Fault,
   tombol *Capture & upload now*.
3. **M11c — sumber nyata (opsional)**: file gambar dan webcam (perubahan header nginx).

## 7. Pengujian

- **Tes Django**:
  - proxy: tanpa login 302, profil orang lain 404, profil bukan device 400;
  - batas ukuran: lebih dari 1 MB → 413;
  - header diteruskan; jawaban 201/415/429 platform diteruskan (`requests.post` di-mock);
  - galat sesi dan platform: platform mati 503, sesi platform habis 401;
  - cache token.
- **Uji manual dengan platform lokal** (port 8000 + 9000):
  1. device board ESP32-CAM, Connect di client, centang *Simulate camera*;
  2. *Capture now* di platform: command #n masuk di client, gambar tampil di kartu Camera dan dashboard;
  3. desired `snapshot_interval = 10`: gambar berkala; `0` menghentikannya;
  4. aturan ECA dengan *Raise alarm* + *Capture snapshot* (Telegram): gambar muncul di daftar alarm
     dan di Telegram;
  5. Fault *Too large* / *Not a JPEG*: galat 413/415 terlihat di client;
  6. Fault *No answer*: command menjadi Expired di platform.

## 8. Keputusan yang perlu diambil

1. Sumber gambar yang dibutuhkan: cukup test pattern, atau juga file/webcam (M11c)?
2. Webcam: boleh mengubah `Permissions-Policy` di server mqtt_client?
3. Platform: tambahkan `snapshot_url` di API v2, atau client cukup menyusun URL dari `PLATFORM_URL`?
