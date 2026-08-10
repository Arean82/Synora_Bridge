"""
Config API views — read/write the runtime config.ini for the System
Configuration GUI. Mirrors the original Flask `/settings` + `/settings/save`
semantics (all sections visible + editable) without its bugs.
"""
import logging

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.services.config_service import get_full_config, update_config

logger = logging.getLogger(__name__)

CONFIG_GET_RESPONSE = inline_serializer(
    "ConfigResponse",
    fields={
        "sections": serializers.JSONField(help_text="Each section -> key -> {value, type}"),
    },
)
CONFIG_PUT_REQUEST = inline_serializer(
    "ConfigUpdateRequest",
    fields={"sections": serializers.JSONField(help_text="Section -> key -> string value")},
)
CONFIG_PUT_RESPONSE = inline_serializer(
    "ConfigUpdateResponse",
    fields={
        "updated": serializers.ListField(child=serializers.CharField()),
        "restart_required": serializers.BooleanField(),
        "restart_keys": serializers.ListField(child=serializers.CharField()),
    },
)


@extend_schema(
    methods=["GET"],
    summary="Read the full runtime configuration",
    responses={200: CONFIG_GET_RESPONSE},
)
@extend_schema(
    methods=["PUT"],
    summary="Update runtime configuration values",
    request=CONFIG_PUT_REQUEST,
    responses={200: CONFIG_PUT_RESPONSE, 400: inline_serializer("ConfigError", fields={"error": serializers.CharField()})},
)
@api_view(["GET", "PUT"])
def config_endpoint(request):
    """GET returns the whole config.ini; PUT applies validated changes."""
    if request.method == "GET":
        return Response({"sections": get_full_config()})

    try:
        sections = request.data.get("sections", {})
        result = update_config(sections)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("Config update failed")
        return Response(
            {"error": "Failed to update configuration. See server logs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response(result)
