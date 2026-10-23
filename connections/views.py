"""
Profil koneksi milik pengguna yang login (tahap M2).

    /connections/                      daftar profil
    /connections/new/[?preset=emqx]    profil baru (kosong, atau dari templat presets.py)
    /connections/<pk>/edit/            ubah profil + langganan tersimpan
    /connections/<pk>/duplicate/       salin profil (POST)
    /connections/<pk>/delete/          hapus (GET konfirmasi, POST hapus)

Setiap query diawali `ConnectionProfile.objects.filter(owner=request.user)`: profil
milik orang lain selalu 404, walaupun nomornya ditebak.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ConnectionProfileForm, SubscriptionFormSet
from .models import ConnectionProfile
from .presets import all_presets


def own_profiles(request):
    return ConnectionProfile.objects.filter(owner=request.user)


@login_required
def profile_list(request):
    profiles = own_profiles(request).prefetch_related("subscriptions")
    return render(request, "connections/profile_list.html", {"profiles": profiles, "presets": all_presets()})


def _save(request, form, formset, created):
    with transaction.atomic():
        profile = form.save(commit=False)
        profile.owner = request.user
        if created:
            profile.position = own_profiles(request).count()
        profile.save()
        formset.instance = profile
        formset.save()
    messages.success(request, f"Connection \"{profile.name}\" was {'created' if created else 'saved'}.")
    return redirect("connections:list")


@login_required
def profile_create(request):
    presets = all_presets()
    # ?preset=<kunci templat>; "other" atau kosong = "Others": form kosong untuk broker lain.
    preset_key = request.GET.get("preset", "")
    preset = presets.get(preset_key)
    initial = preset["data"] if preset else {}
    if request.method == "POST":
        form = ConnectionProfileForm(request.POST, owner=request.user)
        formset = SubscriptionFormSet(request.POST, instance=ConnectionProfile())
        if form.is_valid() and formset.is_valid():
            return _save(request, form, formset, created=True)
    else:
        form = ConnectionProfileForm(initial=initial, owner=request.user)
        formset = SubscriptionFormSet(instance=ConnectionProfile())
    return render(request, "connections/profile_form.html",
                  {"form": form, "formset": formset, "preset": preset, "creating": True,
                   "presets": presets, "preset_key": preset_key if preset else "other"})


@login_required
def profile_edit(request, pk):
    profile = get_object_or_404(own_profiles(request), pk=pk)
    if request.method == "POST":
        form = ConnectionProfileForm(request.POST, instance=profile, owner=request.user)
        formset = SubscriptionFormSet(request.POST, instance=profile)
        if form.is_valid() and formset.is_valid():
            return _save(request, form, formset, created=False)
    else:
        form = ConnectionProfileForm(instance=profile, owner=request.user)
        formset = SubscriptionFormSet(instance=profile)
    return render(request, "connections/profile_form.html",
                  {"form": form, "formset": formset, "profile": profile, "creating": False})


def _copy_name(request, name):
    names = set(own_profiles(request).values_list("name", flat=True))
    for number in range(1, 1000):
        candidate = f"{name} (copy)" if number == 1 else f"{name} (copy {number})"
        if candidate[:80] not in names:
            return candidate[:80]
    return name[:70] + " (copy)"


@login_required
@require_POST
def profile_duplicate(request, pk):
    original = get_object_or_404(own_profiles(request), pk=pk)
    subscriptions = list(original.subscriptions.all())
    with transaction.atomic():
        copy = original
        copy.pk = None              # simpan sebagai baris BARU
        copy.name = _copy_name(request, original.name)
        copy.position = own_profiles(request).count()
        copy.save()
        for subscription in subscriptions:
            subscription.pk = None
            subscription.profile = copy
            subscription.save()
    messages.success(request, f"Created \"{copy.name}\".")
    return redirect("connections:edit", pk=copy.pk)


@login_required
def profile_delete(request, pk):
    profile = get_object_or_404(own_profiles(request), pk=pk)
    if request.method == "POST":
        profile.delete()
        messages.success(request, f"Connection \"{profile.name}\" was deleted.")
        return redirect("connections:list")
    return render(request, "connections/profile_confirm_delete.html", {"profile": profile})
