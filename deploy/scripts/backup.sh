#!/bin/bash
# Backup harian database MQTT Client (dijalankan mqttc-backup.timer sebagai user mqttc).
# Isinya: profil koneksi, langganan, saved messages, akun pengguna (tanpa password: login
# lewat IoT Platform). Disimpan di /srv/mqttc/backups, yang lebih tua dari 14 hari dihapus.
set -euo pipefail
APP=/srv/mqttc/app
DEST=/srv/mqttc/backups
KEEP_DAYS=14
STAMP=$(date +%Y%m%d-%H%M)

# Baca DB_* dari .env tanpa menjalankan isinya sebagai skrip.
get() { grep -E "^$1=" "$APP/.env" | tail -1 | cut -d= -f2-; }
DB_NAME=$(get DB_NAME); DB_USER=$(get DB_USER); DB_PASSWORD=$(get DB_PASSWORD)

umask 077
mkdir -p "$DEST"
# Password lewat variabel lingkungan, bukan argumen (argumen terlihat di `ps`).
# Tabel sesi dan tiket relay tidak perlu dipulihkan: isinya sementara.
MYSQL_PWD="$DB_PASSWORD" mysqldump --single-transaction --no-tablespaces -u "$DB_USER" \
  --ignore-table="$DB_NAME.django_session" --ignore-table="$DB_NAME.connections_relayticket" "$DB_NAME" \
  | gzip > "$DEST/mqttc-db-$STAMP.sql.gz"
find "$DEST" -type f -mtime +"$KEEP_DAYS" -delete
echo "Backup done: $DEST/mqttc-db-$STAMP.sql.gz"
