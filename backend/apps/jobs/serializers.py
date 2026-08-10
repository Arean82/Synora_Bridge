"""Jobs domain serializers (jobs, logs, failed payloads)."""
from rest_framework import serializers

from apps.configs.serializers import TemplateSerializer
from apps.jobs.models import FailedPayload, Job, JobLog


class JobSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    template_detail = TemplateSerializer(source="template", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "template",
            "template_name",
            "template_detail",
            "schedule_interval",
            "is_active",
            "last_run",
            "last_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_run", "last_status", "created_at", "updated_at"]


class JobLogSerializer(serializers.ModelSerializer):
    payload_json = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = JobLog
        fields = ["id", "job", "timestamp", "status", "http_status", "error_message", "payload_json"]
        read_only_fields = fields


class FailedPayloadSerializer(serializers.ModelSerializer):
    payload_json = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = FailedPayload
        fields = ["id", "job", "template", "payload_json", "error_message", "timestamp"]
        read_only_fields = fields
