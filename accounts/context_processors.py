from django.conf import settings


def platform(request):
    """`platform_url` di semua template, mis. tautan "Open IoT Platform"."""
    return {"platform_url": settings.PLATFORM_URL}
