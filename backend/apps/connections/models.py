"""
Connections domain models — API connections (Swagger/OpenAPI specs).

Faithful port of original `SwaggerConnection`: a connection stores a fetched
OpenAPI/Swagger spec (or a local file), its auth configuration, and drives
both the field-mapping UI and the mock server. Auth configs and custom headers
are encrypted at rest.
"""
from django.db import models

from apps.core.fields import EncryptedJSONField, EncryptedTextField


class Connection(models.Model):
    """An API connection with its OpenAPI/Swagger specification."""

    CONNECTION_TYPES = [
        ("rest", "REST"),
        ("graphql", "GraphQL"),
    ]
    AUTH_TYPES = [
        ("none", "None"),
        ("bearer", "Bearer Token"),
        ("api_key", "API Key"),
        ("basic", "Basic Auth"),
    ]
    SCHEMA_SOURCES = [
        ("introspection", "Introspection"),
        ("upload", "Upload"),
    ]

    name = models.CharField(max_length=100)
    url = models.CharField(max_length=500, blank=True, null=True)
    json_content = models.TextField(blank=True, null=True)

    is_local_file = models.BooleanField(default=False)
    local_file_path = models.CharField(max_length=500, blank=True, null=True)

    update_interval_hours = models.IntegerField(default=24)
    is_active = models.BooleanField(default=True)

    connection_type = models.CharField(max_length=50, choices=CONNECTION_TYPES, default="rest")
    sync_schedule = models.CharField(max_length=100, blank=True, null=True)  # hourly|daily|weekly
    environments = models.JSONField(default=list, blank=True)  # [{name, url}]

    # --- Upstream execution auth (used when calling the connection's APIs) ---
    auth_type = models.CharField(max_length=50, choices=AUTH_TYPES, default="none")
    auth_config = EncryptedJSONField(blank=True, null=True)  # {token|header_name|username|...}
    custom_headers = EncryptedJSONField(blank=True, null=True)  # {name: value}

    # --- Spec-fetch auth (dual-auth: fetch spec with different creds) ---
    schema_source = models.CharField(max_length=50, choices=SCHEMA_SOURCES, default="introspection")
    spec_auth_type = models.CharField(max_length=50, choices=AUTH_TYPES, default="none")
    spec_auth_config = EncryptedJSONField(blank=True, null=True)
    spec_custom_headers = EncryptedJSONField(blank=True, null=True)

    # Legacy single-token field (kept for backward compatibility)
    auth_token = EncryptedTextField(blank=True, null=True)

    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
