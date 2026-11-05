# Tahap M8 — Penampil JSON seperti IoT Platform

Payload JSON di daftar pesan (halaman koneksi) kini tampil dengan penampil yang sama dengan
kartu JSON aturan di IoT Platform: nomor baris, warna key/nilai, garis kedalaman, tombol
lipat/buka per object/array, dan *Expand all* / *Collapse all*.

## Kapan dipakai

| Tampilan (pilihan *View*) | Payload | Hasil |
|---|---|---|
| Auto / JSON | object atau array JSON | penampil JSON |
| Auto | angka, string, `true`, teks biasa | teks biasa (seperti sebelumnya) |
| JSON | bukan JSON | `(not JSON) ...` (seperti sebelumnya) |
| Text / Hex / Base64 | apa saja | teks biasa |

Toolbar *Expand all* / *Collapse all* hanya muncul bila JSON lebih dari 12 baris; JSON pendek
(mis. tanda terima `{"publish": 3, "ok": true}`) cukup dengan tombol lipat per baris.

## File

| File | Isi |
|---|---|
| `static/js/json_viewer.js` | salinan `IoT_platform/static/js/json_viewer.js`, ditambah opsi `JsonViewer.create(data, {toolbar: false})` |
| `static/css/app.css` | gaya `.jv-*` dari platform (warna terang/gelap sama) + ukuran ringkas `.message-json` |
| `static/js/session.js` | `payloadElement()` memilih penampil atau teks; `messageElement()` menyimpan elemen per pesan |
| `connections/templates/connections/session.html` | memuat `json_viewer.js` sebelum `session.js` |
| `connections/tests_m8.py` | tes |

## Cache elemen pesan

Daftar pesan digambar ulang setiap ada pesan baru (paling sering sekali per frame). Tanpa
cache, blok yang sudah dilipat pengguna akan terbuka lagi dan penampil JSON dibangun ulang untuk
ratusan pesan. Sekarang elemen tiap pesan disimpan di objek pesan (`message.element`) dan dipakai
lagi selama tampilan (*View*) dan warna langganannya sama; bila salah satunya berubah, elemen
dibuat ulang. Pesan yang terbuang dari batas 2000 pesan ikut membuang elemennya.

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh   # collectstatic untuk json_viewer.js, app.css, session.js
```

Tidak ada migrasi.

Bila `json_viewer.js` di platform diubah, salin ulang ke mqtt_client dan pertahankan opsi
`toolbar`.
