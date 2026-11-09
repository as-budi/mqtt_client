# Tahap M12 — Gaya tampilan Standard / FILKOM

Seperti IoT Platform (`IoT_platform/docs/tahap-26-tambahan-gaya-filkom.md`), MQTT Client kini punya dua
gaya warna yang dipilih per akun, terpisah dari mode Light / Dark / Auto:

- **Standard**: biru, sama dengan gaya Standard platform (tidak berubah).
- **FILKOM**: mengacu pada **FILKOM Apps** (<https://filkom.ub.ac.id/legacy/apps>), bukan gaya FILKOM
  platform (navy `#002647`).

## Warna FILKOM (diambil dari FILKOM Apps)

| Bagian | FILKOM Apps | MQTT Client (FILKOM) |
|---|---|---|
| Bilah atas | `#232E40`, bilah judul `#2D3A50` di bawahnya | `#232E40` dengan pita `#2D3A50` di bawah; nama aplikasi huruf besar berjarak, putih |
| Aksen | ikon oranye `#FB9337` | logo, avatar, pilihan aktif, garis tab aktif, cincin fokus: `#FB9337`; teks oranye di atas putih `#B85D0F` (kontras ±4,6:1) |
| Latar halaman | `#D8DCE3` | sama |
| Kartu | putih, judul huruf besar tebal `#32415A` | sama (judul bagian *Subscriptions*, *Publish*, …) |
| Teks redup | `#868BA1` | `#5F6B80` (digelapkan agar terbaca, ±5,3:1) |
| Tombol utama | tombol *Sign In* slate `#2D3A50` | `#2D3A50`, teks putih; mode gelap: oranye, teks slate |
| Menu akun | dropdown `#202939` | sama |
| Tautan | biru | `#0062CC` |
| Huruf | Roboto | Roboto (gaya Standard tetap Inter) |
| Mode gelap | — | latar `#141B26`, kartu `#1F2938`, garis `#314057` |

Bentuk (sudut membulat) sama dengan gaya Standard; FILKOM Apps bersudut tajam, tetapi aplikasi ini
mengikuti bentuk IoT Platform.

## Memilih gaya

- **Per akun**: bilah atas → **Standard / FILKOM** (layar kecil: menu akun → *Style*). Disimpan di
  `User.ui_style` (migrasi accounts 0002).
- **Bawaan** (`.env`): `UI_STYLE=standard|filkom`, untuk halaman depan dan akun yang belum memilih.
- **Kunci**: `UI_STYLE_SELECTABLE=False` menyembunyikan pilihan; semua akun memakai `UI_STYLE`.

Pilihan di MQTT Client terpisah dari pilihan di IoT Platform.

## Cara kerja

1. `accounts/context_processors.ui_style` menentukan `ui_style` untuk setiap halaman.
2. `templates/base.html` memasang `<html data-ui="...">`; untuk FILKOM memuat Roboto dan
   `static/css/filkom.css` sesudah `app.css`.
3. `filkom.css` hanya mengganti warna dan huruf: variabel `--app-*` / `--bs-*` (terang dan gelap), bilah
   atas, tombol, form, tab. Semua aturan diawali `html[data-ui="filkom"]`.
4. Tombol pilihan: `templates/includes/ui_style_switch.html` → `POST /ui-style/`
   (`accounts.views.ui_style`), lalu kembali ke halaman asal (hanya alamat aplikasi ini).

## File

| File | Isi |
|---|---|
| `accounts/models.py`, `accounts/migrations/0002_user_ui_style.py` | `User.ui_style` |
| `accounts/context_processors.py`, `accounts/views.py`, `accounts/urls.py` | `ui_style`, `POST /ui-style/` |
| `config/settings.py`, `.env.example`, `deploy/env.production.example` | `UI_STYLE`, `UI_STYLE_SELECTABLE` |
| `templates/base.html`, `templates/includes/ui_style_switch.html` | atribut `data-ui`, pilihan gaya |
| `static/css/app.css` | gaya tombol pilihan |
| `static/css/filkom.css` (baru) | warna FILKOM Apps |
| `accounts/tests_ui_style.py` | tes |

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh     # migrasi accounts 0002, collectstatic, restart
```

## Tambahan: identitas laboratorium dan kaki halaman

Sama dengan IoT Platform, di kedua gaya:

- **Nama aplikasi** di bilah atas: logo, **MQTT Client**, dan di bawahnya *Robotic and Embedded System
  Laboratory* (huruf besar kecil, `templates/includes/brand.html`, kelas `.app-brand-name` / `.app-brand-sub`).
  Gaya FILKOM: nama huruf besar berjarak, putih.
- **Kaki halaman** di setiap halaman, rata kanan (layar kecil: kiri):
  *© Computer Engineering Study Program - Faculty of Computer Science - Universitas Brawijaya*
  (`templates/base.html`, `.app-footer`). Selalu di bawah layar walau isi halaman pendek. Gaya Standard:
  warna kartu, garis tipis; gaya FILKOM: slate gelap `#232E40` dengan garis `#2D3A50`.

Tes: `accounts/tests_ui_style.py` (`IdentityTests`).
