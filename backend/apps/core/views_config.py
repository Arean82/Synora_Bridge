"""
Config API views — read/write the runtime config.ini for the System
Configuration GUI. Mirrors the original original `/settings` + `/settings/save`
semantics (all sections visible + editable) without its bugs.

Core-settings restart: a save that touches restart-required keys triggers a
VALIDATED in-place restart — the running daphne re-executes itself (os.execl)
after the response flushes, so the same console keeps running; no manual
stop/start. A pre-flight `manage.py check` runs first: if the new config would
not boot, the restart is blocked and the error is returned instead (the server
stays up on the old config).
"""
import logging
import os
import sys
import threading
import time

from drf_spectacular.utils import extend_schema, inline_serializer
import rest_framework.exceptions
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.services.config_service import (
    get_full_config,
    update_config,
    verify_postgres_connection,
)

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


# ---------------------------------------------------------------------------
# Validated in-place restart (auto-apply on core saves)
# ---------------------------------------------------------------------------
def _config_boots(backend_dir, timeout=90):
    """Run `manage.py check` against the CURRENT (just-saved) config.

    Returns (ok, error). A failed check means the saved config would refuse to
    boot (production invariants, invalid timezone, bad DB engine, ...) — the
    auto-restart must NOT fire, or the server would go down and stay down.
    """
    import subprocess

    try:
        proc = subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — surface the failure to the UI
        return False, f"pre-flight check failed: {exc}"
    if proc.returncode == 0:
        return True, ""
    return False, (proc.stdout or "manage.py check failed").strip()[:500]


def _schedule_restart(host, port, delay=0.75):
    """Re-exec daphne in place after `delay` seconds.

    Runs in a daemon thread so the HTTP response is flushed first. os.execl
    replaces THIS process — the same console keeps running the restarted daphne
    (no manual stop/start, logs stay visible). Celery is a separate process and
    is not affected.
    """

    def _restart():
        time.sleep(delay)
        from config.ini_config import BACKEND_DIR

        os.chdir(BACKEND_DIR)
        os.execl(
            sys.executable,
            sys.executable,
            "-m", "daphne",
            "-b", str(host),
            "-p", str(port),
            "config.asgi:application",
        )

    threading.Thread(target=_restart, daemon=True).start()


def _restart_if_boots(host, port):
    """Validate the config boots, then schedule the in-place restart.

    Returns (ok, error).
    """
    from config.ini_config import BACKEND_DIR

    ok, error = _config_boots(BACKEND_DIR)
    if not ok:
        return False, error
    _schedule_restart(host, port)
    return True, ""


def _daphne_bind():
    """(host, port) daphne should rebind on, from config.ini [Server]."""
    from config.ini_config import get_config_dict

    server = get_config_dict().get("Server", {})
    return server.get("host", "127.0.0.1"), server.get("port", "8000")


def _auto_restart_enabled():
    """Auto-restart on save is a production behavior; tests disable it so a
    core-key PUT can never re-exec the test runner (os.execl)."""
    from django.conf import settings

    return getattr(settings, "AUTO_RESTART_ON_SAVE", True)


def _maybe_auto_restart(restart_keys):
    """When restart-required keys changed, validate + schedule the restart.

    Merged into the PUT response:
      {"restart_scheduled": true, "restart_in_seconds": 0.75, "restart_keys": [...]}
    or, when the new config would NOT boot:
      {"restart_blocked": {"keys": [...], "error": "..."}}
    """
    if not restart_keys or not _auto_restart_enabled():
        return {}
    host, port = _daphne_bind()
    ok, error = _restart_if_boots(host, port)
    if not ok:
        return {"restart_blocked": {"keys": restart_keys, "error": error}}
    return {
        "restart_scheduled": True,
        "restart_in_seconds": 0.75,
        "restart_keys": restart_keys,
        "celery_restart_required": any(key.startswith("CELERY.") for key in restart_keys),
    }


RESTART_RESPONSE = inline_serializer(
    "ConfigRestartResponse",
    fields={
        "status": serializers.CharField(),
        "detail": serializers.CharField(required=False),
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
        result.update(_maybe_auto_restart(result.get("restart_keys", [])))
    except rest_framework.exceptions.APIException:
        # Malformed payloads etc. — let DRF render its own 400, not a 500.
        raise
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
    methods=["POST"],
    summary="Restart the backend now (daphne re-executes itself in place)",
    responses={202: RESTART_RESPONSE, 400: RESTART_RESPONSE},
)
@api_view(["POST"])
def restart_endpoint(request):
    """Manually trigger the validated in-place daphne restart.

    Frontend calls this when the user wants a restart without a core save, or
    after a blocked auto-restart was fixed. Same pre-flight gate as the
    auto-restart: if the current config would not boot, nothing restarts.
    """
    host, port = _daphne_bind()
    if not _auto_restart_enabled():
        return Response(
            {"status": "blocked", "detail": "Auto-restart is disabled for this environment."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    ok, error = _restart_if_boots(host, port)
    if not ok:
        return Response(
            {"status": "blocked", "detail": error},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {"status": "restarting", "detail": f"daphne -b {host} -p {port} config.asgi:application"},
        status=status.HTTP_202_ACCEPTED,
    )


VERIFY_DB_REQUEST = inline_serializer(
    "VerifyDbRequest",
    fields={
        "host": serializers.CharField(required=False),
        "port": serializers.CharField(required=False),
        "database": serializers.CharField(required=False),
        "username": serializers.CharField(required=False),
        "password": serializers.CharField(required=False, write_only=True),
    },
)
VERIFY_DB_RESPONSE = inline_serializer(
    "VerifyDbResponse",
    fields={
        "ok": serializers.BooleanField(),
        "error": serializers.CharField(required=False, help_text="Set when ok is false"),
    },
)


@extend_schema(
    methods=["POST"],
    summary="Verify a PostgreSQL connection (never persists anything)",
    request=VERIFY_DB_REQUEST,
    responses={200: VERIFY_DB_RESPONSE},
)
@api_view(["POST"])
def verify_db_endpoint(request):
    """Test the supplied POSTGRES values with a real connection attempt.

    Stateless by design: nothing is written to config.ini and credentials are
    never logged. Missing fields fall back to the values currently on disk, so
    the Settings GUI can test with partial edits.
    """
    from config.ini_config import get_config_dict

    current = get_config_dict().get("POSTGRES", {})
    merged = {
        "host": request.data.get("host") or current.get("host", "localhost"),
        "port": request.data.get("port") or current.get("port", "5432"),
        "database": request.data.get("database") or current.get("database", "bridge_db"),
        "username": request.data.get("username") or current.get("username", "postgres"),
        "password": request.data.get("password") or current.get("password", ""),
    }
    ok, err = verify_postgres_connection(
        host=merged["host"],
        port=merged["port"],
        database=merged["database"],
        username=merged["username"],
        password=merged["password"],
    )
    if ok:
        return Response({"ok": True})
    return Response({"ok": False, "error": err})


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
