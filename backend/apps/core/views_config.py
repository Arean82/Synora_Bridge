"""
Config API views — read/write the runtime config.ini for the System
Configuration GUI. Mirrors the original original `/settings` + `/settings/save`
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


@extend_schema(
    summary="Read a project documentation file (README.md / docs/*.md) as sanitized HTML",
    responses={200: inline_serializer("DocContent", fields={"filename": serializers.CharField(), "content": serializers.CharField()})},
)
@api_view(["GET"])
def doc_content(request, filename):
    """Serve markdown docs rendered to SANITIZED HTML (reference-repo pattern).

    Renders Markdown server-side with the full extension set (tables, fenced
    code, codehilite, sane lists) then strips unsafe HTML with bleach, so the
    frontend displays trusted HTML — no client-side markdown/XSS surface.
    README.md is served from the repo root; everything else from docs/.
    Traversal is rejected (hardened: the original only blocked `..` and `/`).
    """
    from pathlib import Path

    import bleach
    import markdown
    from config.ini_config import BACKEND_DIR as BACKEND_PKG_DIR

    repo_root = BACKEND_PKG_DIR.parent
    docs_dir = repo_root / "docs"

    name = Path(filename).name
    if name != filename or ".." in filename or "\\" in filename:
        return Response({"error": "Invalid filename."}, status=status.HTTP_400_BAD_REQUEST)

    if name == "README.md":
        target = repo_root / name
    else:
        target = docs_dir / name
    if not name.endswith(".md") or not target.exists():
        return Response({"error": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        raw = target.read_text(encoding="utf-8")
        html = markdown.markdown(
            raw,
            extensions=["extra", "tables", "fenced_code", "codehilite", "sane_lists", "toc"],
        )
        safe_html = bleach.clean(
            html,
            tags=[
                "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
                "strong", "em", "del", "code", "pre", "blockquote",
                "ul", "ol", "li", "dl", "dt", "dd",
                "table", "thead", "tbody", "tr", "th", "td",
                "a", "img", "span", "div",
            ],
            attributes={
                "a": ["href", "title", "target", "rel"],
                "img": ["src", "alt", "title"],
                "code": ["class"],
                "th": ["align"], "td": ["align"],
                "span": ["class"],
            },
            protocols=["http", "https", "mailto"],
        )
        return Response({"filename": name, "content": safe_html})
    except Exception:
        logger.exception("Failed to render doc %s", name)
        return Response({"error": "Failed to render document."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id="email_templates_list",
    summary="List email templates",
    responses={200: inline_serializer("EmailTemplateList", fields={"templates": serializers.ListField(child=serializers.CharField())})},
)
@api_view(["GET"])
def email_templates_list(request):
    """List the available email template filenames."""
    from apps.core.services.email_templates import list_templates

    return Response({"templates": list_templates()})


@extend_schema(
    methods=["GET"],
    operation_id="email_template_retrieve",
    summary="Read one email template",
    responses={200: inline_serializer("EmailTemplateRead", fields={"filename": serializers.CharField(), "content": serializers.CharField()})},
)
@extend_schema(
    methods=["PUT"],
    operation_id="email_template_update",
    summary="Save one email template",
    request=inline_serializer("EmailTemplateWrite", fields={"content": serializers.CharField()}),
    responses={200: inline_serializer("EmailTemplateSaved", fields={"filename": serializers.CharField(), "saved": serializers.BooleanField()})},
)
@api_view(["GET", "PUT"])
def email_template_detail(request, filename):
    """GET reads a template; PUT saves its content."""
    from apps.core.services.email_templates import read_template, write_template

    try:
        if request.method == "GET":
            content = read_template(filename)
            return Response({"filename": filename, "content": content})
        content = request.data.get("content", "")
        write_template(filename, content)
        return Response({"filename": filename, "saved": True})
    except FileNotFoundError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("Email template operation failed")
        return Response(
            {"error": "Failed to operate on template. See server logs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
