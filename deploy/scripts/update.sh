#!/bin/bash
# Memperbarui MQTT Client di server setelah ada perubahan kode (jalankan dengan sudo):
#   sudo /srv/mqttc/app/deploy/scripts/update.sh
# Urutan: ambil kode -> pasang paket -> cek -> migrasi -> file statis -> restart.
# Bila satu langkah gagal, skrip berhenti dan layanan lama tetap berjalan.
set -euo pipefail
APP=/srv/mqttc/app
VENV=/srv/mqttc/venv
as_mqttc() { sudo -u mqttc -H "$@"; }

cd "$APP"
echo "==> git pull"
as_mqttc git -C "$APP" pull --ff-only
echo "==> pip install"
as_mqttc "$VENV/bin/pip" install --quiet -r requirements.txt
echo "==> check --deploy"
as_mqttc "$VENV/bin/python" manage.py check --deploy --fail-level WARNING
echo "==> migrate"
as_mqttc "$VENV/bin/python" manage.py migrate --noinput
echo "==> collectstatic"
as_mqttc "$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0
echo "==> restart"
systemctl restart mqttc.target
sleep 2
systemctl --no-pager --lines=0 status mqttc-web mqttc-relay | grep -E "●|Active:" || true
echo "Done."
