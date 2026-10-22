"""
Pengguna aplikasi MQTT Client.

Aplikasi ini TIDAK punya pendaftaran atau password sendiri. Setiap pengguna berasal
dari IoT Platform: saat pertama kali login (OpenID Connect), baris User dibuat dari
data id_token, lalu diperbarui setiap login berikutnya (accounts/oidc.py).

Pengguna dikenali dari `platform_sub` (klaim "sub" = id pengguna di platform), BUKAN
dari username: username bisa diganti Admin platform, sedangkan "sub" tidak pernah berubah.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    platform_sub = models.CharField(
        "IoT Platform user id", max_length=64, unique=True, null=True, blank=True,
        help_text="The \"sub\" claim from IoT Platform. Empty for local admin accounts.",
    )

    @property
    def display_name(self):
        return self.get_full_name() or self.username
