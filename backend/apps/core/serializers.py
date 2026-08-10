"""Core domain serializers (app settings, audit log)."""
from rest_framework import serializers

from apps.core.models import AppSetting, AuditLog


class AppSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSetting
        fields = ["id", "key", "value", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "transaction_id",
            "mode",
            "caller",
            "bytes_transferred",
            "record_count",
            "status",
            "timestamp",
            "payload_json",
            "endpoint",
            "template",
        ]
        read_only_fields = fields
