"""
Sisi Django dari relay WebSocket -> TCP (tahap M4).

Untuk RELAY (proses lain di server yang sama, lihat paket relay/):

    POST /internal/relay/redeem/   {"ticket": "..."}  -> tujuan koneksi, tiket ditandai terpakai
    POST /internal/relay/report/   {"ticket": "...", "failure": "...", "detail": "..."}

Untuk BROWSER (pengguna yang login):

    GET  /connections/relay/<id>/status/   kenapa koneksi relay gagal, untuk pesan yang jelas

Endpoint internal dilindungi dua lapis:
    1. header X-Relay-Secret harus sama dengan RELAY_SHARED_SECRET (.env);
    2. permintaan yang datang lewat Nginx (ada header X-Forwarded-For) ditolak. Nginx juga
       menjawab 404 untuk /internal/ (lihat deploy/nginx). Relay memanggil Django langsung
       di 127.0.0.1, tanpa Nginx.
"""
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import RelayTicket

FAILURES = {
    "bad_request": "The relay received something that is not an MQTT connection.",
    "ticket_invalid": "The connection ticket expired or was already used. Try connecting again.",
    "address_not_allowed": "The relay may not connect to this address (private networks and other "
                           "ports are blocked).",
    "unreachable": "The broker could not be reached. Check the host and port.",
    "tls_failed": "The TLS handshake with the broker failed (invalid or self-signed certificate?).",
    "too_many": "You have too many relay connections open. Close one and try again.",
    "busy": "The relay is busy. Try again later.",
}


def _authorized(request):
    secret = settings.RELAY_SHARED_SECRET
    given = request.headers.get("X-Relay-Secret", "")
    return bool(secret) and hmac.compare_digest(given, secret) and "X-Forwarded-For" not in request.headers


def _body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


@csrf_exempt
@require_POST
def redeem(request):
    if not _authorized(request):
        raise Http404
    token = str(_body(request).get("ticket", ""))
    oldest = timezone.now() - timedelta(seconds=settings.RELAY_TICKET_SECONDS)
    ticket = RelayTicket.objects.filter(token_hash=RelayTicket.hash(token)).select_related("user").first()
    # UPDATE bersyarat: dua relay yang menukar tiket yang sama bersamaan, hanya satu yang berhasil.
    claimed = ticket is not None and RelayTicket.objects.filter(
        pk=ticket.pk, used_at__isnull=True, created_at__gte=oldest, user__is_active=True,
    ).update(used_at=timezone.now())
    if not claimed:
        return JsonResponse({"error": "ticket_invalid"}, status=404)
    return JsonResponse({
        "ticket_id": ticket.pk, "user_id": ticket.user_id, "username": ticket.user.username,
        "host": ticket.host, "port": ticket.port, "tls": ticket.tls, "ca_pem": ticket.ca_pem,
    })


@csrf_exempt
@require_POST
def report(request):
    if not _authorized(request):
        raise Http404
    data = _body(request)
    failure = str(data.get("failure", ""))
    if failure not in FAILURES:
        return JsonResponse({"error": "unknown failure"}, status=400)
    RelayTicket.objects.filter(token_hash=RelayTicket.hash(str(data.get("ticket", "")))).update(
        failure=failure, failure_detail=str(data.get("detail", ""))[:200])
    return JsonResponse({"ok": True})


@login_required
@require_GET
def status(request, pk):
    ticket = get_object_or_404(RelayTicket, pk=pk, user=request.user)
    return JsonResponse({
        "used": ticket.used_at is not None,
        "failure": ticket.failure or None,
        "message": FAILURES.get(ticket.failure, ""),
        "detail": ticket.failure_detail,
    })
