# Tahap M6: Pohon topik, grafik, MQTT 5, ekspor, CA sendiri

Tahap ini membantu **membaca** lalu lintas MQTT, bukan hanya mengirimnya:

- tab **Topics**: pohon topik dengan jumlah pesan dan nilai terakhir;
- tab **Charts**: grafik garis kecil untuk setiap angka di pesan;
- **properti MQTT 5** saat publish, dan tampilannya saat menerima;
- **ekspor** pesan ke JSON atau CSV;
- **CA sendiri** untuk broker `mqtts://` bersertifikat self-signed (lewat relay).

Semua analisis berjalan **di browser**. Pesan tidak dikirim ke server aplikasi dan hilang saat
halaman ditutup, kecuali diekspor.

## 1. Tab Topics, Charts, List

Di atas daftar pesan ada tiga tab:

| Tab | Isi |
|---|---|
| List | daftar pesan seperti tahap M3 (filter, arah, tampilan payload, Pause) |
| Topics | pohon topik: setiap level `/` menjadi cabang, dengan jumlah pesan (masuk dan keluar) dan nilai terakhir di daun. Klik nama → kembali ke List dengan filter topik itu |
| Charts | satu grafik untuk setiap deret angka: payload angka (`23.5`) atau kunci angka/boolean di objek JSON (`{"temperature": 23.5}` → `topik › temperature`). Tampil nilai terakhir, min, max, jumlah titik |

Batas di memori browser: 2000 pesan terakhir untuk ekspor (List menampilkan 500 terakhir yang lolos filter), 120 titik terakhir per grafik.
Tab yang terbuka diperbarui otomatis saat pesan datang (paling sering sekali per frame layar).

## 2. Properti MQTT 5

Bila profil memakai **MQTT 5** (*Protocol version* di form profil), bagian *MQTT 5 properties*
muncul di kartu Publish:

| Isian | Properti MQTT 5 | Kegunaan |
|---|---|---|
| Content type | `contentType` | memberi tahu penerima format payload, mis. `application/json` |
| Expiry (s) | `messageExpiryInterval` | pesan (termasuk retained) dibuang broker setelah N detik |
| Response topic | `responseTopic` | pola request/response: penerima menjawab ke topik ini |
| User properties | `userProperties` | pasangan `key=value` bebas, satu per baris |

Properti pesan yang **diterima** tampil di baris keterangan pesan, mis.
`QoS 1 · 42 B · 10:01:02 · content-type application/json, response lab/reply, source=sim`.

Pada MQTT 3.1.1 bagian ini disembunyikan, karena protokol itu tidak punya properti.

## 3. Ekspor

Tombol **Export** di kartu Messages:

| Format | Isi |
|---|---|
| JSON | larik objek `{time, direction, topic, qos, retain, payload, encoding, properties}` |
| CSV (Excel) | kolom `time, direction, topic, qos, retain, payload, encoding`, UTF-8 dengan BOM supaya Excel membaca huruf non-ASCII dengan benar |

`direction` bernilai `received` atau `published`. `encoding` bernilai `utf-8` bila payload teks, atau `base64` bila payload biner (payload
lalu ditulis dalam base64). Nama berkas: `mqtt-<nama-profil>-<waktu>.json` / `.csv`.

## 4. CA sendiri untuk `mqtts://`

Broker praktikum sering memakai sertifikat **self-signed** atau CA kampus sendiri. Lewat jalur
Relay, sertifikat itu sekarang bisa diterima dengan menempelkan **sertifikat CA** (PEM) di kolom
*CA certificate* pada form profil. Kolom ini hanya muncul untuk skema `mqtts://`.

- CA ini **ditambahkan** ke daftar CA bawaan sistem; nama host tetap diperiksa.
- Form menolak teks yang bukan sertifikat, dan menolak **private key** (yang ditempel hanya
  sertifikat publik).
- Untuk `wss://` (Direct), sertifikat diperiksa oleh browser sendiri; tidak ada yang bisa diubah
  aplikasi. Pasang CA-nya di sistem operasi, atau buka `https://host:port` sekali dan terima
  sertifikatnya.

Alurnya: profil (`ca_pem`) → tiket relay (`RelayTicket.ca_pem`) → `redeem` → relay memuatnya
dengan `ssl.SSLContext.load_verify_locations(cadata=…)`. CA yang rusak menghasilkan
`tls_failed` dengan rincian *the custom CA certificate is not valid*.

Mengambil CA dari broker (contoh):

```bash
# CA yang dipakai Mosquitto biasanya ada di file cafile pada mosquitto.conf, mis. /etc/mosquitto/certs/ca.crt
openssl s_client -connect broker.lab.local:8883 -showcerts </dev/null
```

## 5. Berkas yang berubah

| Berkas | Isi |
|---|---|
| `connections/models.py`, migrasi `0003` | `ConnectionProfile.ca_pem`, `RelayTicket.ca_pem` |
| `connections/forms.py` | `clean_ca_pem()` (harus sertifikat sah, bukan private key), dikosongkan bila bukan `mqtts` |
| `connections/relay_api.py`, `relay/server.py` | CA ikut di tiket dan dimuat relay |
| `connections/templates/connections/session.html` | tab, MQTT 5 properties, Export |
| `static/js/session.js` | `topicStats`, `series`, `renderTree()`, `renderCharts()`, `publishProperties()`, ekspor |
| `static/js/connection_form.js` | kolom CA hanya untuk `mqtts` |
| `relay/tests.py` | `TlsRelayTests`: broker TLS self-signed ditolak tanpa CA, diterima dengan CA |
| `connections/tests_m56.py` | `CustomCaTests` |
