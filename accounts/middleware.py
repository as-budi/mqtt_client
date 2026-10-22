"""
Menjaga sesi tetap sejalan dengan IoT Platform.

Setiap request dari pengguna yang login: bila access token platform sudah (hampir)
kedaluwarsa, perbarui dengan refresh token. Bila platform menolak, artinya pengguna
mencabut izin aplikasi ini (Connected apps), akunnya dinonaktifkan, atau sesinya
dicabut. Pengguna lalu di-logout dari aplikasi ini juga, paling lambat sekitar 10 menit
(umur access token) setelah kejadian.

Platform sedang tidak bisa dihubungi -> pengguna TIDAK di-logout (aplikasi tetap bisa
dipakai untuk broker lain); dicoba lagi paling cepat 60 detik kemudian.
"""
import time

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from . import platform

RETRY_KEY = "platform_retry_at"
RETRY_SECONDS = 60


class PlatformSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.platform_sub:
            response = self.check(request)
            if response is not None:
                return response
        return self.get_response(request)

    def check(self, request):
        token = platform.stored_token(request)
        if token is None:
            return self.end(request)
        if not platform.is_expired(token) or time.time() < request.session.get(RETRY_KEY, 0):
            return None
        try:
            platform.refresh(request)
            request.session.pop(RETRY_KEY, None)
        except platform.PlatformUnavailable:
            request.session[RETRY_KEY] = time.time() + RETRY_SECONDS
        except platform.PlatformSessionEnded:
            return self.end(request)
        return None

    def end(self, request):
        logout(request)
        messages.info(request, "Your IoT Platform session has ended. Please sign in again.")
        return redirect("accounts:welcome")
