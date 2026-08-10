"""Django admin registrations for the jobs domain."""
from django.contrib import admin

from apps.jobs.models import FailedPayload, Job, JobLog


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "schedule_interval", "is_active", "last_run", "last_status")
    list_filter = ("is_active",)
    search_fields = ("template__name",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(JobLog)
class JobLogAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "timestamp", "status", "http_status")
    list_filter = ("status",)
    search_fields = ("job__id",)


@admin.register(FailedPayload)
class FailedPayloadAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "template", "timestamp", "error_message")
    search_fields = ("job__id", "template__name")
