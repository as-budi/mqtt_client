"""URL utama aplikasi MQTT Client."""
from django.contrib import admin
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import include, path

from connections import relay_api

def favicon(request):
    """/favicon.ico -> logo MQTT Client (browser dan aplikasi lain sering langsung memintanya)."""
    return redirect(static("img/favicon.ico"))


urlpatterns = [
    path("favicon.ico", favicon),
    # Situs admin Django: hanya untuk superuser LOKAL (createsuperuser), bukan pengguna platform.
    path("admin/", admin.site.urls),
    # /connections/...  profil koneksi broker, halaman koneksi
    path("connections/", include("connections.urls")),
    # Hanya untuk relay di server yang sama (tahap M4); Nginx menjawab 404 untuk /internal/.
    path("internal/relay/redeem/", relay_api.redeem, name="relay_redeem"),
    path("internal/relay/report/", relay_api.report, name="relay_report"),
    # /docs/  dokumentasi pengguna (tahap M13), bisa dibaca tanpa login
    path("docs/", include("userdocs.urls")),
    # /  halaman depan, /login/, /oidc/callback/, /logout/
    path("", include("accounts.urls")),
]
