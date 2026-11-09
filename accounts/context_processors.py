from django.conf import settings


def ui_style(request):
    """`ui_style` = "standard" atau "filkom": pilihan akun bila boleh memilih, selain itu bawaan .env."""
    style = settings.UI_STYLE
    user = getattr(request, "user", None)
    if (settings.UI_STYLE_SELECTABLE and user is not None and user.is_authenticated
            and user.ui_style in settings.UI_STYLES):
        style = user.ui_style
    return {"ui_style": style, "ui_style_selectable": settings.UI_STYLE_SELECTABLE}


def platform(request):
    """`platform_url` di semua template, mis. tautan "Open IoT Platform"."""
    return {"platform_url": settings.PLATFORM_URL}
