"""
Bersih-bersih harian (tahap M7), dijalankan mqttc-cleanup.timer:

    python manage.py cleanup            # tiket relay > 1 hari + sesi kedaluwarsa
    python manage.py cleanup --days 7

- Tiket relay hanya berguna beberapa detik (ditukar relay, lalu dibaca browser bila gagal).
  Yang tua dihapus supaya tabelnya tidak terus membesar.
- Sesi Django yang kedaluwarsa (berisi token platform yang sudah tidak berlaku) dihapus
  dengan perintah bawaan `clearsessions`.
"""
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from connections.models import RelayTicket


class Command(BaseCommand):
    help = "Delete old relay tickets and expired sessions."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=1, help="Keep relay tickets this many days (default 1).")

    def handle(self, *args, days, **options):
        oldest = timezone.now() - timedelta(days=max(days, 0))
        deleted, _ = RelayTicket.objects.filter(created_at__lt=oldest).delete()
        call_command("clearsessions")
        self.stdout.write(f"Deleted {deleted} relay ticket(s) older than {days} day(s); expired sessions cleared.")
