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
2. **Tanda terima otomatis** — kotak centang *Acknowledge rule JSON automatically* di bagian
   otomatisasi device (halaman sesi, aktif secara bawaan). `handleRule()` di
   `static/js/session.js` meniru firmware ESP32:
   - pesan kosong (aturan dicabut) → tidak dijawab;
   - JSON valid dengan `"type": "rule"` dan blok `rule` → `{"publish": <id>, "ok": true, "size": <byte>, "rule": "<nama>"}`;
   - JSON rusak → `{"ok": false, "error": "invalid JSON"}`;
   - MAC di `device.mac` berbeda dengan MAC device ini → `ok: false`, `"MAC address does not match this device"`.
3. **Tombol contoh** *Rule ack* di daftar topik device (ganti `{id}` dengan nomor aturan) untuk
   mengirim tanda terima secara manual, misalnya bila kotak centang dimatikan.

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
