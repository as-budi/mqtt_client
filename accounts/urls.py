"""Halaman depan, login (OpenID Connect), logout."""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.welcome, name="welcome"),
    path("login/", views.login_start, name="login"),
    # Alamat ini didaftarkan di platform sebagai redirect URI (harus sama persis).
    path("oidc/callback/", views.callback, name="callback"),
    path("logout/", views.logout_view, name="logout"),
]
