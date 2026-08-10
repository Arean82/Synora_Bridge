"""Configs domain serializers (bridge templates)."""
from django.conf import settings
from rest_framework import serializers
from timezone_field.rest_framework import TimeZoneSerializerField

from apps.configs.models import Template


class TemplateSerializer(serializers.ModelSerializer):
    slug = serializers.ReadOnlyField()
    # EncryptedJSONField columns map to TextField for DRF's field inference;
    # declare them explicitly so the API exposes real JSON objects.
    sources = serializers.JSONField(required=True)
    destinations = serializers.JSONField(default=list)
    client_credentials = serializers.JSONField(default=dict)
    # Validated IANA timezone (per-template override of [Server] timezone).
    # Explicit default mirrors the model field so omitted values still
    # serialize as the configured zone instead of None.
    timezone = TimeZoneSerializerField(required=False, default=settings.TIME_ZONE)

    class Meta:
        model = Template
        fields = [
            "id",
            "name",
            "slug",
            "timezone",
            "execution_mode",
            "pull_method",
            "partner_url",
            "partner_auth_token",
            "sources",
            "client_name",
            "client_url",
            "client_auth_type",
            "client_credentials",
            "destinations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sources(self, value):
        if not value:
            raise serializers.ValidationError("At least one source endpoint is required.")
        for idx, src in enumerate(value):
            if not isinstance(src, dict):
                raise serializers.ValidationError(f"Source {idx + 1} must be an object.")
            source_type = src.get("source_type", "rest")
            if not src.get("url"):
                raise serializers.ValidationError(f"Source {idx + 1} must have a URL.")
            if source_type == "rest" and not src.get("selectedApi"):
                raise serializers.ValidationError(f"Source {idx + 1} must have a selected API endpoint.")
            if source_type == "graphql" and not src.get("graphql_query"):
                raise serializers.ValidationError(f"Source {idx + 1} must have a GraphQL query.")
        return value
