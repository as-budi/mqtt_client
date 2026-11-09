# Tahap M13 — Dokumentasi pengguna dan favicon

## 1. Dokumentasi pengguna (`/docs/`)

MQTT Client kini punya dokumentasi pengguna dengan **tampilan dan cara kerja yang sama** dengan
dokumentasi IoT Platform (`IoT_platform/userdocs`, tahap 25):

- kiri: menu tiga tingkat *Section Navigation* (bagian → bab → judul bagian di dalam bab);
- tengah: isi bab, *breadcrumb*, tautan bab sebelum/sesudah;
- kanan (layar lebar): *On this page*, dengan bagian yang sedang dibaca disorot;
- kotak pencarian di atas (`/docs/search/?q=...`), hasil dengan cuplikan dan kata yang disorot.

Bisa dibaca tanpa login. Tautan **Documentation** ada di bilah atas setiap halaman dan di halaman
depan. Isinya berbahasa Inggris, seperti antarmuka aplikasi.

| Bagian | Bab |
|---|---|
| Basics | Getting started · MQTT in a nutshell · Your account and display |
| Connections | Connection profiles · IoT Platform devices and sandbox |
| Messages | Subscribe and publish · Reading messages |
| Simulating devices | Behaving like a device · Camera simulator (ESP32-CAM) |
| Help | Troubleshooting |

Angka di dalam bab diambil dari pengaturan server (`userdocs/context.py`): alamat IoT Platform dan
brokernya, port dan batas relay, batas pesan tersimpan, batas unggahan kamera, apakah gaya bisa dipilih.

Menambah bab: buat `userdocs/templates/userdocs/pages/<slug>.html` (judul bagian `<h2 id="...">`),
lalu tambahkan satu `Page(...)` di `userdocs/pages.py`. Placeholder seperti `{{counter}}` ditulis
`{% templatetag openvariable %}counter}}` agar tidak dibaca sebagai variabel template.

## 2. Favicon

Ikon tab browser memakai logo MQTT Client (dua panah), warnanya mengikuti gaya:

| Gaya | Ikon |
|---|---|
| Standard | kotak gradasi biru → hijau toska, panah putih |
| FILKOM | kotak oranye `#FB9337`, panah slate `#232E40` |

Berkas di `static/img/`: `favicon-<gaya>.svg`, `favicon-<gaya>-32.png`, `apple-touch-icon-<gaya>.png`,
dan `favicon.ico` (16 + 32 px). `/favicon.ico` dialihkan ke berkas statis itu.

## File

| File | Isi |
|---|---|
| `userdocs/` (app baru) | `pages.py`, `context.py`, `search.py` (sama dengan platform), `views.py`, `urls.py`, templat, `tests.py` |
| `config/settings.py`, `config/urls.py` | app `userdocs`, `/docs/`, `/favicon.ico` |
| `templates/base.html` | tautan Documentation, ikon tab browser |
| `accounts/templates/accounts/welcome.html` | tautan ke dokumentasi |
| `static/css/app.css`, `static/css/filkom.css` | gaya `.docs-*` (dari platform), `--app-surface-2`, tautan di bilah atas |
| `static/img/` | favicon |

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh     # collectstatic, restart; tidak ada migrasi
```
