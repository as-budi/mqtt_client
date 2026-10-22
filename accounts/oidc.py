"""
Login dengan akun IoT Platform lewat OpenID Connect (pustaka Authlib).

Alur (lihat docs/tahap-m2-kerangka-dan-login.md):

    1. /login/          -> authorize_redirect(): Authlib membuat state, nonce, dan PKCE
                           (code_verifier disimpan di sesi), lalu mengalihkan browser ke
                           <issuer>/authorize/ di platform.
    2. platform         -> pengguna login dan menyetujui izin, lalu kembali ke
                           /oidc/callback/?code=...&state=...
    3. /oidc/callback/  -> authorize_access_token(): cek state, tukar code + code_verifier
                           + client secret di <issuer>/token/, periksa tanda tangan dan isi
                           id_token (iss, aud, nonce, exp) dengan kunci publik platform.
    4. sync_user()      -> buat/perbarui User lokal dari klaim id_token.

Semua alamat platform dibaca otomatis dari dokumen "discovery"
<issuer>/.well-known/openid-configuration, jadi cukup issuer yang diatur di .env.
"""
from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.db import transaction

from .models import User

oauth = OAuth()
oauth.register(
    name="platform",
    client_id=settings.OIDC_CLIENT_ID,
    client_secret=settings.OIDC_CLIENT_SECRET,
    server_metadata_url=f"{settings.OIDC_ISSUER}/.well-known/openid-configuration",
    client_kwargs={
        "scope": settings.OIDC_SCOPES,
        # PKCE (S256): diwajibkan platform; Authlib membuat code_verifier sendiri.
        "code_challenge_method": "S256",
        "timeout": settings.PLATFORM_TIMEOUT,
    },
)


def platform_client():
    return oauth.create_client("platform")


@transaction.atomic
def sync_user(claims):
    """User lokal untuk klaim id_token `claims` (dibuat bila belum ada).

    Username mengikuti platform. Bila username itu kebetulan masih dipakai pengguna
    lokal LAIN (pengguna platform lama yang sudah berganti nama), pengguna lama itu
    diberi nama sementara "<username>~<sub>" sampai ia login lagi.
    """
    sub = str(claims["sub"])
    username = claims.get("preferred_username") or f"user-{sub}"
    user = User.objects.select_for_update().filter(platform_sub=sub).first()
    if user is None:
        user = User(platform_sub=sub)
        user.set_unusable_password()       # tidak pernah login dengan password di sini

    clash = User.objects.filter(username=username).exclude(pk=user.pk).first()
    if clash is not None:
        clash.username = f"{username}~{clash.platform_sub or clash.pk}"[:150]
        clash.save(update_fields=["username"])

    user.username = username
    user.first_name = claims.get("given_name", "")[:150]
    user.last_name = claims.get("family_name", "")[:150]
    user.email = claims.get("email", "")
    user.is_active = True
    user.save()
    return user
