"""
Pengaturan aplikasi "MQTT Client" (repo mqtt_client).

Aplikasi web untuk menguji dan belajar MQTT: profil koneksi, subscribe, publish.
Pengguna login dengan akun IoT Platform (OpenID Connect); aplikasi ini TIDAK punya
pendaftaran atau password sendiri. Rancangan: docs/rencana-mqtt-client.md.

Semua nilai yang berbeda antara laptop dan server dibaca dari file .env.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# --- Keamanan dasar ---------------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key-ganti-di-env")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]


# --- App --------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # App milik project ini:
    "accounts",      # pengguna (dari IoT Platform), login OpenID Connect, token platform
    "connections",   # profil koneksi broker MQTT dan langganan tersimpan
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Memperbarui token IoT Platform yang kedaluwarsa; logout bila akun dicabut/dinonaktifkan.
    "accounts.middleware.PlatformSessionMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.platform",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database ---------------------------------------------------------------
# MySQL, database TERPISAH dari IoT Platform (mis. mqttc) walaupun di server yang sama.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "mqttc"),
        "USER": os.getenv("DB_USER", "mqttc_user"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Pengguna dan login -------------------------------------------------------

# Pengguna dibuat otomatis saat pertama kali login dari IoT Platform (accounts/oidc.py).
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:welcome"          # halaman "Sign in with IoT Platform"
LOGIN_REDIRECT_URL = "connections:list"

# Nama cookie DIBEDAKAN dari IoT Platform. Di laptop keduanya berjalan di 127.0.0.1
# (port 8000 dan 9000), dan cookie TIDAK dipisahkan per port: dengan nama yang sama
# ("sessionid"), login di satu aplikasi akan menimpa sesi aplikasi lainnya.
SESSION_COOKIE_NAME = "mqttc_sessionid"
CSRF_COOKIE_NAME = "mqttc_csrftoken"
# Sesi di database server (bawaan Django): token IoT Platform yang disimpan di sesi
# tidak pernah dikirim ke browser; cookie hanya berisi id sesi acak.
SESSION_COOKIE_AGE = 14 * 24 * 3600     # sama dengan umur refresh token platform


# --- IoT Platform (penyedia login, OpenID Connect) ------------------------------
# Lihat docs/tahap-m2-kerangka-dan-login.md dan, di repo IoT_platform,
# docs/tahap-22-login-untuk-aplikasi-lain.md.

# Alamat IoT Platform, mis. https://iot.reslab-csub.cloud (laptop: http://127.0.0.1:8000).
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
# Issuer OpenID Connect = PLATFORM_URL + "/o" (harus sama dengan OIDC_ISSUER di platform).
OIDC_ISSUER = (os.getenv("OIDC_ISSUER", "") or f"{PLATFORM_URL}/o").rstrip("/")
# Dari `python manage.py oauth_client "MQTT Client" --redirect-uri .../oidc/callback/` di platform.
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid profile email devices:read")
# Batas waktu (detik) setiap permintaan ke platform.
PLATFORM_TIMEOUT = float(os.getenv("PLATFORM_TIMEOUT", "10"))


# --- Bahasa, waktu, file statis -------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.getenv("DJANGO_STATIC_ROOT", "") or BASE_DIR / "staticfiles")


# --- Produksi ---------------------------------------------------------------------

if not DEBUG:
    from django.core.exceptions import ImproperlyConfigured

    if SECRET_KEY.startswith("dev-only") or len(SECRET_KEY) < 40:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in .env to a long random value (50+ characters).")
    if not (OIDC_CLIENT_ID and OIDC_CLIENT_SECRET):
        raise ImproperlyConfigured("Set OIDC_CLIENT_ID and OIDC_CLIENT_SECRET in .env.")

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if os.getenv("DJANGO_HTTPS", "False") == "True":
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
        SECURE_SSL_REDIRECT = False          # dikerjakan Nginx
        SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W005", "security.W021"]
    SESSION_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"plain": {"format": "{levelname} {name}: {message}", "style": "{"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
        "root": {"handlers": ["console"], "level": "INFO"},
    }

# Saat tes, permintaan sungguhan ke platform tidak boleh terjadi (tes memakai tiruan).
TESTING = sys.argv[1:2] == ["test"]
