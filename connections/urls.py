"""Profil koneksi. Semua diawali /connections/ (lihat config/urls.py)."""
from django.urls import path

from . import platform_devices, relay_api, saved, session, views

app_name = "connections"

urlpatterns = [
    path("", views.profile_list, name="list"),
    path("new/", views.profile_create, name="create"),
    path("<int:pk>/edit/", views.profile_edit, name="edit"),
    path("<int:pk>/duplicate/", views.profile_duplicate, name="duplicate"),
    path("<int:pk>/delete/", views.profile_delete, name="delete"),
    # Tahap M3: halaman koneksi (MQTT di browser) dan bahan connect.
    path("<int:pk>/", session.session_page, name="session"),
    path("<int:pk>/connect/", session.connect_info, name="connect"),
    path("<int:pk>/saved/", saved.saved_list, name="saved"),
    path("saved/<int:pk>/delete/", saved.saved_delete, name="saved_delete"),
    # Tahap M3: profil dari device IoT Platform.
    path("platform/", platform_devices.device_list, name="platform"),
    path("platform/sandbox/", platform_devices.sandbox_create, name="platform_sandbox"),
    path("platform/<int:device_id>/", platform_devices.device_create, name="platform_create"),
    # Tahap M4: status tiket relay (kenapa koneksi gagal).
    path("relay/<int:pk>/status/", relay_api.status, name="relay_status"),
]
