"""
"Saved messages": pesan publish yang disimpan untuk dipakai lagi (tahap M3). API JSON
untuk halaman koneksi (static/js/session.js).

    GET  /connections/<pk>/saved/        pesan milik pengguna: untuk profil ini + untuk semua profil
    POST /connections/<pk>/saved/        simpan pesan baru (JSON)
    POST /connections/saved/<id>/delete/ hapus
"""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from .models import ConnectionProfile, Qos, SavedMessage

MAX_SAVED = 200


@login_required
@require_http_methods(["GET", "POST"])
def saved_list(request, pk):
    profile = get_object_or_404(ConnectionProfile, pk=pk, owner=request.user)
    messages = SavedMessage.objects.filter(owner=request.user).filter(Q(profile=profile) | Q(profile__isnull=True))
    if request.method == "GET":
        return JsonResponse({"messages": [m.as_dict() for m in messages]})

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if SavedMessage.objects.filter(owner=request.user).count() >= MAX_SAVED:
        return JsonResponse({"error": f"You can keep at most {MAX_SAVED} saved messages."}, status=400)
    message = SavedMessage(
        owner=request.user,
        profile=None if data.get("allConnections") else profile,
        name=str(data.get("name", "")).strip()[:80],
        topic=str(data.get("topic", "")),
        payload=str(data.get("payload", "")),
        qos=data.get("qos", 0) if data.get("qos") in Qos.values else 0,
        retain=bool(data.get("retain")),
    )
    try:
        message.full_clean(exclude=["owner", "profile"])
    except ValidationError as exc:
        return JsonResponse({"error": "; ".join(f"{k}: {' '.join(v)}" for k, v in exc.message_dict.items())},
                            status=400)
    message.save()
    return JsonResponse(message.as_dict(), status=201)


@login_required
@require_POST
def saved_delete(request, pk):
    get_object_or_404(SavedMessage, pk=pk, owner=request.user).delete()
    return JsonResponse({"ok": True})
