"""Django admin registrations for the core domain."""
from django.contrib import admin

from apps.core.models import AppSetting, AuditLog


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("transaction_id", "mode", "caller", "status", "timestamp")
    list_filter = ("mode", "status")
    search_fields = ("transaction_id", "caller", "endpoint")
    readonly_fields = ("transaction_id", "timestamp")
