from django.contrib import admin

from .models import ConnectionProfile, SubscriptionPreset


class SubscriptionInline(admin.TabularInline):
    model = SubscriptionPreset
    extra = 0


@admin.register(ConnectionProfile)
class ConnectionProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "scheme", "host", "port", "updated_at")
    list_filter = ("scheme",)
    search_fields = ("name", "host", "owner__username")
    inlines = [SubscriptionInline]
