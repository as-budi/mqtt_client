"""Mengenali paket MQTT CONNECT (MQTT 3.1, 3.1.1, dan 5) dari byte pertama koneksi.

Struktur awal paket CONNECT:

    byte 0         0x10 = jenis CONNECT (4 bit atas = 1) dengan flag 0
    byte 1..4      "remaining length", bilangan variabel: 7 bit per byte, bit 8 = masih ada lanjutan
    2 byte         panjang nama protokol
    n byte         nama protokol: "MQTT" (3.1.1 dan 5) atau "MQIsdp" (3.1)
"""


def is_connect_packet(data):
    if len(data) < 2 or data[0] != 0x10:
        return False
    index, length, multiplier = 1, 0, 1
    while True:
        if index >= len(data) or index > 4:
            return False
        byte = data[index]
        length += (byte & 0x7F) * multiplier
        multiplier *= 128
        index += 1
        if not byte & 0x80:
            break
    if len(data) < index + 2:
        return False
    name_length = int.from_bytes(data[index:index + 2], "big")
    name = bytes(data[index + 2:index + 2 + name_length])
    return name in (b"MQTT", b"MQIsdp") and length >= 2 + name_length
