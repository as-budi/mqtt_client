"""
Relay WebSocket -> TCP untuk broker mqtt:// dan mqtts:// (tahap M4).

Browser hanya bisa membuka WebSocket. Untuk broker yang hanya punya port TCP (1883, 8883),
mqtt.js di browser menyambung ke relay ini lewat WebSocket, lalu relay membuka koneksi TCP
(atau TLS) ke broker dan meneruskan BYTE apa adanya di kedua arah. Relay tidak memahami
topik atau pesan; protokol MQTT tetap dijalankan mqtt.js di browser.

Jalankan:  python -m relay      (pengaturan dari .env, lihat relay/config.py)

    browser --wss://.../relay/<tiket>--> relay :8003 --TCP/TLS--> broker:1883/8883
                                           |
                                           +--POST /internal/relay/redeem/--> Django (tiket -> tujuan)

Pengaman (docs/tahap-m4-relay.md):
    - tiket sekali pakai dari Django; alamat tujuan tidak pernah datang dari browser;
    - hanya meneruskan bila paket pertama adalah MQTT CONNECT (bukan terowongan TCP umum);
    - hanya port 1883/8883 (bisa ditambah) ke alamat IP PUBLIK (bukan localhost/LAN/metadata);
    - batas koneksi per pengguna dan total, batas laju, batas diam, batas umur koneksi.

Paket ini sengaja TIDAK memakai Django: kecil, cepat, dan mudah diperiksa.
"""
