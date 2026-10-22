"""
Aturan nama topik MQTT (spesifikasi MQTT 3.1.1 bagian 4.7 dan MQTT 5 bagian 4.7).

Topik NAMA (untuk publish, mis. Last Will):
    - tidak kosong, maksimal 65535 byte UTF-8;
    - tidak boleh berisi wildcard "+" atau "#";
    - tidak boleh berisi karakter NUL.

Topik FILTER (untuk subscribe):
    - "#" hanya boleh sendirian atau di level TERAKHIR, mis. "iot/#" (bukan "iot/#/x");
    - "+" harus mengisi SATU level penuh, mis. "iot/+/telemetry" (bukan "iot/a+");
    - "$share/<grup>/<filter>" (langganan bersama, MQTT 5) diterima apa adanya.

Contoh valid:   iot/abc/telemetry    iot/+/status    #    +/+/errors
Contoh salah:   iot/#/x   iot/a+   (kosong)
"""
from django.core.exceptions import ValidationError

MAX_TOPIC_BYTES = 65535


def _common(value):
    if not value:
        raise ValidationError("The topic cannot be empty.")
    if "\x00" in value:
        raise ValidationError("The topic cannot contain a NUL character.")
    if len(value.encode("utf-8")) > MAX_TOPIC_BYTES:
        raise ValidationError("The topic is longer than 65535 bytes.")


def validate_topic_name(value):
    _common(value)
    if "+" in value or "#" in value:
        raise ValidationError("A topic you publish to cannot contain the wildcards + or #.")


def validate_topic_filter(value):
    _common(value)
    levels = value.split("/")
    if levels[0] == "$share" and len(levels) >= 3:
        levels = levels[2:]
    for index, level in enumerate(levels):
        if "#" in level and (level != "#" or index != len(levels) - 1):
            raise ValidationError('"#" must be a whole level and the last one, e.g. "iot/#".')
        if "+" in level and level != "+":
            raise ValidationError('"+" must fill a whole level, e.g. "iot/+/telemetry".')
