# Tahap M7 — JSON aturan dari IoT Platform

Pasangan dari `IoT_platform/docs/tahap-26-tambahan-publish-rule.md`. Tombol **Publish to
devices** di halaman aturan platform mengirim JSON aturan utuh ke setiap device aturan. MQTT
client kini bisa berperan sebagai device itu, sehingga publish dapat diuji tanpa ESP32.

## Topik

| Topik | Arah | Keterangan |
|---|---|---|
| `{prefix}/{token}/rules/+` | platform → device | JSON aturan, retained, QoS 1; pesan kosong = dicabut |
| `{prefix}/{token}/rules/<rule id>/ack` | device → platform | tanda terima |

Kedua topik diambil dari API platform (`topics.rules` dan `topics.rule_ack`), seperti topik
device lainnya; token tidak disimpan di database.

## Perubahan

1. **Langganan profil device** — `DEVICE_SUBSCRIPTIONS` (`connections/platform_devices.py`)
   ditambah `{prefix}/{token}/rules/+` (QoS 1, ungu). Migrasi data
   `connections/0004_rule_topic_subscription` menambahkannya ke profil device platform yang
   sudah ada (sekali saja; profil broker biasa tidak disentuh).
2. **Balasan otomatis dan manual** di bagian otomatisasi device (halaman sesi):
   - kotak centang *Acknowledge rule JSON automatically* (aktif secara bawaan);
   - **template balasan**, bawaan `{"publish": {{publish}}, "ok": true, "size": {{size}}}`,
     dengan placeholder `{{id}}` (nomor aturan), `{{publish}}`, `{{rev}}`, `{{size}}` (byte),
     `{{rule}}` (nama aturan), `{{mac}}`. Teks di-escape seperti string JSON, jadi aman ditaruh
     di dalam tanda kutip. Ubah menjadi `"ok": false, "error": "..."` untuk menguji status
     *Rejected* di platform;
   - tombol **Reply now**: mengirim template untuk JSON aturan terakhir yang diterima (berguna
     bila kotak centang dimatikan, mis. untuk menguji device yang tidak membalas lalu membalas
     belakangan); tombol **Reset** mengembalikan template bawaan;
   - baris info: aturan terakhir, nomor publish, ukuran, dan masalah bila ada.

   `handleRule()` / `readRule()` / `replyRule()` di `static/js/session.js` meniru firmware
   ESP32: pesan kosong (aturan dicabut) tidak dijawab; JSON rusak dijawab
   `{"ok": false, "error": "invalid JSON"}` dan MAC di `device.mac` yang berbeda dijawab
   `"MAC address does not match this device"` — keduanya selalu `ok: false`, tidak memakai
   template.
3. **Tombol contoh** *Rule ack* di daftar topik device (ganti `{id}` dengan nomor aturan) untuk
   mengirim tanda terima lewat form Publish biasa.

## Uji coba

1. Di platform, buka aturan → **Publish to devices**. Status device: *Sent* (atau *Queued*
   bila bridge belum jalan).
2. Di MQTT client, buka koneksi untuk setiap device aturan (Platform devices → device) dan
   Connect. Pesan retained `rules/<id>` langsung masuk dan client membalas ack.
3. Kartu publish di platform berubah menjadi *Received* (atau *Rejected* beserta alasannya).

Karena pesan retained, setiap Connect ulang menerima JSON lagi dan membalas lagi — perilaku
yang sama dengan device sungguhan; platform cukup memperbarui waktu balasan.

## Tes

```bash
python manage.py test connections
```

`connections/tests_m7.py` (migrasi data, kotak centang, skrip) dan
`connections/tests_session.py` (langganan profil baru).

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh   # pull, pip, migrate (connections 0004), collectstatic, restart
```

Perbarui platform lebih dulu: tanpa `topics.rules` dari API platform, client tidak mengenali
topik aturan dan kotak centang tidak berpengaruh.
