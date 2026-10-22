from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PlatformUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "platform_sub", "is_staff", "last_login")
    search_fields = ("username", "email", "platform_sub")
    fieldsets = UserAdmin.fieldsets + (("IoT Platform", {"fields": ("platform_sub",)}),)
    readonly_fields = ("platform_sub",)
