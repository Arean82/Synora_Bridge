"""Django admin registrations for the connections domain."""
from django.contrib import admin

from apps.connections.models import Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "url", "connection_type", "is_active", "last_updated")
    list_filter = ("connection_type", "is_active")
    search_fields = ("name", "url")
    readonly_fields = ("id", "last_updated", "created_at")
