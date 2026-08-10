"""Django admin registrations for the configs domain."""
from django.contrib import admin

from apps.configs.models import Template


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "execution_mode", "pull_method", "created_at")
    list_filter = ("execution_mode",)
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
