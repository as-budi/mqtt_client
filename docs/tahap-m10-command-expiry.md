# Tahap M10 — Command yang sudah kedaluwarsa

Pasangan dari `IoT_platform/docs/tahap-26-tambahan-command-expiry.md`. Pesan command dari
platform kini membawa batas waktunya:

```json
{"id": 12, "method": "blink", "params": {"times": 5}, "expires_at": 1762412345, "ttl": 297}
```

- `expires_at`: batas waktu dalam Unix time (detik sejak 1970, UTC).
- `ttl`: sisa detik saat platform mengirim pesan.

Auto-responder di halaman koneksi device (*Answer commands automatically* dan *Simulate
firmware updates*) kini meniru template firmware ESP32: bila jam browser sudah melewati
`expires_at` lebih dari 2 detik, command **tidak dijalankan dan tidak dijawab**. Platform
sudah menandainya *Expired*, dan jawaban yang terlambat toh ditolak. Baris keterangan di bawah
template jawaban menyebut command yang dilewati.

Command tanpa `expires_at` (platform versi lama) dijawab seperti sebelumnya.

## File

| File | Isi |
|---|---|
| `static/js/session.js` | `commandExpired()`, dipanggil di `automate()` sebelum OTA dan jawaban |
| `connections/templates/connections/session.html` | baris `auto-command-info` |
| `connections/tests_m10.py` | tes |

## Update server

```bash
sudo /srv/mqttc/app/deploy/scripts/update.sh   # collectstatic
```

Tidak ada migrasi.
