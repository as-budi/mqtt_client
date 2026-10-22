"""URL utama aplikasi MQTT Client."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Situs admin Django: hanya untuk superuser LOKAL (createsuperuser), bukan pengguna platform.
    path("admin/", admin.site.urls),
    # /connections/...  profil koneksi broker
    path("connections/", include("connections.urls")),
    # /  halaman depan, /login/, /oidc/callback/, /logout/
    path("", include("accounts.urls")),
]
