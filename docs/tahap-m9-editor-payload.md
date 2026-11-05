# Tahap M9 — Editor payload JSON di kartu Publish

Bila format payload di kartu Publish diubah ke **JSON**, kotak payload tampil seperti code
editor, senada dengan penampil JSON di daftar pesan (tahap M8). Format **Text** tetap textarea
biasa.

## Fitur

- **Nomor baris** di kiri, ikut menggulir. Baris tempat JSON rusak ditandai merah (hanya bila
  payload tanpa placeholder; dengan placeholder, pesan error tetap tampil di bawah kotak).
- **Warna** key, string, angka, dan `true/false/null` sama dengan penampil JSON.
- **Placeholder** `{{counter}}`, `{{random:20:30}}`, `{{timestamp}}`, ... diberi warna oranye,
  baik di luar maupun di dalam string.
- **Tab** menyisipkan 2 spasi; **Enter** mempertahankan indentasi (tambah 2 spasi setelah `{`
  atau `[`). Ctrl/⌘+Enter tetap mengirim pesan.
- Tab **Edit / Preview**: Preview menampilkan penampil JSON berlipat (nomor baris, lipat/buka,
  Expand/Collapse all) dari payload yang placeholder-nya sudah diisi contoh.
- Baris tidak dibungkus (gulir ke samping) supaya nomor baris selalu sejajar.

## Cara kerja

`static/js/payload_editor.js` (`PayloadEditor.attach`) memakai cara yang sama dengan editor impor
di IoT Platform: textarea tetap textarea (teksnya transparan, kursor tetap terlihat) dan di
belakangnya ada `<pre>` berwarna dengan font, ukuran, tinggi baris, dan padding yang sama. Yang
dikirim tetap `textarea.value`, jadi publish, riwayat, pesan tersimpan, dan publish berulang
tidak berubah.

`session.js` memanggil `payloadEditor.refresh()` di `checkPayload()`, yang sudah dipanggil
setiap kali payload atau format berubah — termasuk lewat kode (`fillPublish`, tombol Format,
tombol contoh topik device, pesan tersimpan).

Semua teks dimasukkan setelah di-escape (`escapeHtml`), jadi payload seperti `<script>` tampil
sebagai teks.

## File

| File | Isi |
|---|---|
| `static/js/payload_editor.js` | editor (baru) |
| `static/js/session.js` | `PayloadEditor.attach(...)`, `jsonErrorLine()`, refresh di `checkPayload()` |
| `static/css/app.css` | gaya `.pe-*` |
| `connections/templates/connections/session.html` | memuat `payload_editor.js` |
| `connections/tests_m9.py` | tes |

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh   # collectstatic
```

Tidak ada migrasi.
