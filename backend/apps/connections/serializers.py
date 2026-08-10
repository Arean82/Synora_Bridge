"""Connections domain serializers (API connections)."""
from rest_framework import serializers

from apps.connections.models import Connection


class ConnectionSerializer(serializers.ModelSerializer):
    # EncryptedJSONField columns map to TextField for DRF's field inference;
    # declare them explicitly so the API exposes real JSON objects.
    auth_config = serializers.JSONField(required=False, allow_null=True)
    custom_headers = serializers.JSONField(required=False, allow_null=True)
    spec_auth_config = serializers.JSONField(required=False, allow_null=True)
    spec_custom_headers = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Connection
        fields = [
            "id",
            "name",
            "url",
            "json_content",
            "is_local_file",
            "local_file_path",
            "update_interval_hours",
            "is_active",
            "connection_type",
            "sync_schedule",
            "environments",
            "auth_type",
            "auth_config",
            "custom_headers",
            "schema_source",
            "spec_auth_type",
            "spec_auth_config",
            "spec_custom_headers",
            "auth_token",
            "last_updated",
            "created_at",
        ]
        read_only_fields = ["id", "last_updated", "created_at"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Name is required.")
        return value.strip()
