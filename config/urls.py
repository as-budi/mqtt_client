"""URL utama aplikasi MQTT Client."""
from django.contrib import admin
from django.urls import include, path

from connections import relay_api

urlpatterns = [
    # Situs admin Django: hanya untuk superuser LOKAL (createsuperuser), bukan pengguna platform.
    path("admin/", admin.site.urls),
    # /connections/...  profil koneksi broker, halaman koneksi
    path("connections/", include("connections.urls")),
    # Hanya untuk relay di server yang sama (tahap M4); Nginx menjawab 404 untuk /internal/.
    path("internal/relay/redeem/", relay_api.redeem, name="relay_redeem"),
    path("internal/relay/report/", relay_api.report, name="relay_report"),
    # /  halaman depan, /login/, /oidc/callback/, /logout/
    path("", include("accounts.urls")),
]
