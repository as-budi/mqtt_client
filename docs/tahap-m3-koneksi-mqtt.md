# Tahap M3: Koneksi MQTT di browser

Setelah tahap ini aplikasi benar-benar menjadi MQTT client. Pengguna bisa:

- membuka profil dan menekan **Connect**;
- subscribe dan unsubscribe;
- melihat pesan masuk dan keluar;
- publish;
- menyimpan pesan yang sering dipakai;
- tersambung **sebagai device IoT Platform**.

Broker WebSocket (`wss://`, misalnya `broker.emqx.io:8084`) disambung langsung dari browser.
Broker TCP (`mqtt://`, `mqtts://`) lewat relay (tahap M4).

## 1. Pembagian kerja

```
Browser (static/js/session.js + mqtt.js)                Django (connections/session.py)
──────────────────────────────────────────              ─────────────────────────────────
klik Connect ──────── POST /connections/<pk>/connect/ ─▶ bahan connect (JSON):
                                                          url, clientId, username,
                                                          [password device], Last Will,
                                                          langganan, topik device
mqtt.connect(url, {...})  ═════ MQTT over WebSocket ═════▶ broker (Direct) / relay (M4)
subscribe, publish, terima pesan: semuanya di browser
```

Protokol MQTT dijalankan **mqtt.js 5.15.2** di browser (`static/vendor/mqtt.min.js`, disimpan
di repo, tanpa CDN). Server tidak pernah melihat pesan, dan tidak pernah melihat password broker
biasa: password diketik di halaman lalu langsung dipakai mqtt.js.

Bahan connect diminta lagi **setiap** connect dan reconnect, karena:

- client ID dibuat acak setiap kali (awalan profil + 8 heksadesimal), supaya dua tab tidak
  saling menendang;
- tiket relay (M4) hanya berlaku sekali;
- token device IoT Platform diambil saat itu juga dari API platform.

Karena itu reconnect dikerjakan sendiri oleh `session.js` (`reconnectPeriod: 0` di mqtt.js),
dengan jeda 1, 2, 5, 10, 20, 30 detik. Penolakan yang tidak akan sembuh dengan mencoba lagi
**tidak** diulang, misalnya password salah, tidak diizinkan, atau alamat relay diblokir.

## 2. Halaman koneksi

| Bagian | Isi |
|---|---|
| Kepala | nama, alamat, jalur (Direct/Relay), status (Connected, Reconnecting in N s, ...), password (bila profil punya username), *Remember here* |
| Subscriptions | daftar dengan QoS dan status: ✓ diterima, *refused* ditolak broker (SUBACK 0x80, mis. karena ACL); *mute* menyembunyikan pesannya; ✕ unsubscribe |
| Publish | topik (saran dari riwayat dan topik device), payload, format Text/JSON (divalidasi, tombol *Format*), QoS, Retain, **Ctrl+Enter** |
| | *History* (20 terakhir, di browser), *Saved* (di server), *Clear retained* (publish payload kosong + retain, dengan konfirmasi) |
| Messages | terbaru di atas; filter topik/teks (tombol `/`), arah, tampilan Auto/Text/JSON/Hex/Base64, Pause, Clear; per pesan: Copy topic, Copy payload, Publish again |

Batas: 2.000 pesan per halaman di memori, dan 500 terakhir yang digambar. Penggambaran dilakukan
paling sering sekali per frame layar (`requestAnimationFrame`), jadi ratusan pesan per detik
tidak membuat halaman macet.

**Keamanan tampilan.** Payload dari broker bisa berisi apa saja, termasuk `<script>`. Semua teks
pesan dipasang dengan `textContent`, tidak pernah `innerHTML`, sehingga tidak ada yang bisa
berjalan sebagai kode di halaman.

**Password "Remember here"** disimpan di `localStorage` browser itu saja, dan siapa pun yang
memakai browser itu bisa membacanya. Bawaannya tidak dicentang.

## 3. Tersambung sebagai device IoT Platform

**Connections → From IoT Platform** menampilkan device milik pengguna dan yang dibagikan
kepadanya. Datanya dari `GET /api/v2/me/devices` platform, dengan token OAuth pengguna (tahap
M2). **Create connection** membuat profil yang:

- mengarah ke broker platform: WebSocket bila platform punya `MQTT_PUBLIC_WS_URL`, kalau tidak
  `mqtts://` lewat relay;
- login sebagai device (username = password = access token);
- berlangganan `{prefix}/{token}/desired`, `.../commands/+`, `.../errors`.

Token **tidak** disimpan di aplikasi ini. Profil hanya mengingat id device, dan topiknya ditulis
dengan `{prefix}` dan `{token}`. Saat Connect, server mengambil token dan prefix dari API platform
lalu mengisinya. Bila token di-*regenerate* di platform, profil tetap jalan. Bila pengguna
kehilangan akses Editor, Connect ditolak dengan pesan yang jelas.

Di halaman koneksinya muncul tombol **Device topics**: *Telemetry*, *Online*, *Firmware*,
*Command response*. Tombol ini mengisi topik dan contoh payload, sehingga mahasiswa bisa
mencoba dashboard, aturan, dan command platform tanpa ESP32.

Peringatan: profil ini berbagi identitas dengan device sungguhan. Pesan yang dipublish dari sini
diterima platform seolah-olah dari device itu.

## 4. Saved messages

Disimpan di server (model `SavedMessage`), bisa untuk satu koneksi atau **semua koneksi**
pengguna. API JSON:

| Alamat | Isi |
|---|---|
| `GET/POST /connections/<pk>/saved/` | daftar dan simpan |
| `POST /connections/saved/<id>/delete/` | hapus |

Maksimal 200 per pengguna. Topik dengan wildcard ditolak.

## 5. Yang ditambahkan

| File | Isi |
|---|---|
| `connections/session.py` | halaman koneksi, `connect_info` (bahan connect) |
| `connections/platform_devices.py` | daftar device platform, buat profil device |
| `connections/saved.py` | API saved messages |
| `connections/models.py` | `SavedMessage` (dan `RelayTicket`, M4); migrasi `0002` |
| `templates/connections/session.html`, `platform_devices.html` | tampilan |
| `static/js/session.js` | seluruh logika MQTT di browser |
| `static/vendor/mqtt.min.js` | mqtt.js 5.15.2 |
| `connections/tests_session.py` | tes |

## 6. Mencoba

Jalankan seperti tahap M2. Lalu **New connection → EMQX public broker → Create**, **Open**,
**Connect**. Subscribe `filkom/test/#`, lalu publish ke `filkom/test/hello`. Pesan keluar (↑)
dan masuk (↓) muncul di kanan.

Pengujian yang sudah dilakukan dengan broker uji lokal (WebSocket + TCP) dan IoT Platform di
laptop:

- password salah → "Wrong username or password";
- langganan yang ditolak → *refused*;
- publish/terima JSON;
- payload berisi HTML tampil sebagai teks;
- koneksi lewat relay, dan port terlarang ditolak tanpa mengulang;
- profil device platform tersambung dengan token dari API, dan tombol Telemetry mengirim data.
