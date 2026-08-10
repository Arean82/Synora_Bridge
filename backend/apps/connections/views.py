"""
Connections domain viewsets.

CRUD mirrors original `connection_controller.py`; `toggle` and `refresh` fetch
the spec from the connection URL. The mock server and spec-validation actions
live in apps.pull (Phase 4) since they generate endpoints/schemas.
"""
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.connections.models import Connection
from apps.connections.serializers import ConnectionSerializer
from apps.connections.services import fetch_swagger_json
from apps.core.exceptions import APIError


def _build_headers(conn):
    """Assemble upstream request headers from connection auth config."""
    headers = dict(conn.custom_headers or {})
    cfg = conn.auth_config or {}
    if conn.auth_type == "bearer" and cfg.get("token"):
        headers["Authorization"] = f"Bearer {cfg['token']}"
    elif conn.auth_type == "api_key" and cfg.get("header_name") and cfg.get("header_value"):
        headers[cfg["header_name"]] = cfg["header_value"]
    elif conn.auth_type == "basic" and cfg.get("username") and cfg.get("password"):
        import base64

        creds = f"{cfg['username']}:{cfg['password']}"
        headers["Authorization"] = "Basic " + base64.b64encode(creds.encode()).decode()
    return headers


class ConnectionViewSet(viewsets.ModelViewSet):
    """CRUD for API connections (Swagger/OpenAPI specs)."""

    queryset = Connection.objects.all()
    serializer_class = ConnectionSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def _fetch_and_store_spec(self, conn):
        headers = _build_headers(conn)
        json_data, _actual_url = fetch_swagger_json(conn.url, headers=headers)
        import json

        conn.json_content = (
            json.dumps(json_data) if isinstance(json_data, dict) else json_data
        )
        conn.is_active = True
        conn.last_updated = timezone.now()
        conn.save()

    def perform_create(self, serializer):
        conn = serializer.save()
        self._post_save_fetch(conn)

    def perform_update(self, serializer):
        conn = serializer.save()
        self._post_save_fetch(conn)

    def _post_save_fetch(self, conn):
        """Fetch initial JSON if a URL is provided (skips GraphQL/local files)."""
        if conn.connection_type == "graphql":
            conn.is_active = True
            conn.save(update_fields=["is_active"])
        elif conn.url and not conn.is_local_file:
            try:
                self._fetch_and_store_spec(conn)
            except Exception:
                conn.is_active = False
                conn.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        """Re-fetch the spec from the connection URL."""
        conn = self.get_object()
        if conn.connection_type == "graphql":
            raise APIError("GraphQL connections cannot be refreshed.", 400)
        if conn.is_local_file:
            raise APIError("Cannot refresh local file connections from a URL.", 400)
        try:
            self._fetch_and_store_spec(conn)
            return Response(self.get_serializer(conn).data)
        except Exception as e:
            raise APIError(str(e), 400)

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        """Enable/disable a connection; enabling re-validates the spec."""
        conn = self.get_object()
        target_state = request.data.get("is_active", not conn.is_active)
        if target_state and not conn.is_local_file and conn.connection_type != "graphql":
            try:
                self._fetch_and_store_spec(conn)
            except Exception as e:
                conn.is_active = False
                conn.save(update_fields=["is_active"])
                raise APIError(
                    f"Failed to fetch Swagger JSON: {e}. Connection remains disabled.", 400
                )
        else:
            conn.is_active = target_state
            conn.save(update_fields=["is_active"])
        return Response(self.get_serializer(conn).data)

    @action(detail=False, methods=["post"])
    def validate(self, request):
        """Validate an OpenAPI/Swagger spec (port of original /connections/validate).

        POST body:
          source_type: 'url' | 'file' | 'paste'
          url:         the spec URL when source_type == 'url'
          content:     spec text for 'file'/'paste'
          spec_auth_type / spec_auth_config / spec_custom_headers: optional
                        dual-auth headers used only to fetch the spec.
        Returns {success, title, api_version, spec_version, operation_count,
                 schema_count} or {success: false, error}.
        """
        import base64
        import json

        from apps.connections.services.openapi_validator import OpenAPIValidator

        data = request.data or {}
        source_type = data.get("source_type")
        content = data.get("content")
        url = data.get("url")

        auth_headers = dict(data.get("spec_custom_headers") or {})
        auth_type = data.get("spec_auth_type", "none")
        auth_config = data.get("spec_auth_config") or {}

        if auth_type == "bearer" and auth_config.get("token"):
            auth_headers["Authorization"] = f"Bearer {auth_config['token']}"
        elif auth_type == "api_key" and auth_config.get("header_name") and auth_config.get("header_value"):
            auth_headers[auth_config["header_name"]] = auth_config["header_value"]
        elif auth_type == "basic" and auth_config.get("username") and auth_config.get("password"):
            creds = f"{auth_config['username']}:{auth_config['password']}"
            auth_headers["Authorization"] = "Basic " + base64.b64encode(creds.encode()).decode()

        validator = OpenAPIValidator()

        if source_type == "url":
            result = validator.process_and_validate(url=url, auth_headers=auth_headers)
        elif source_type in ("file", "paste"):
            result = validator.process_and_validate(content=content)
        else:
            return Response(
                {"success": False, "error": "Invalid source_type specified"},
                status=400,
            )

        if result.get("success"):
            return Response(result)
        return Response(result, status=400)
