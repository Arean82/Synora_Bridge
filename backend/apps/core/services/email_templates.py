"""
Email template service — list/read/write the failure-alert templates.

Port of the original `htmx_email_templates*` endpoints with one hardening:
filename is validated to stay inside the email templates directory
(the original only checked the `.html` suffix, allowing `../` traversal).
"""
from pathlib import Path

from django.conf import settings

EMAIL_TEMPLATE_DIR = Path(settings.BASE_DIR) / "templates" / "email"


def _safe_path(filename: str) -> Path:
    """Resolve a filename and verify it stays inside the email dir."""
    if not filename or Path(filename).name != filename:
        raise ValueError("Invalid template filename.")
    if not filename.endswith(".html"):
        raise ValueError("Template filename must end with .html.")
    candidate = (EMAIL_TEMPLATE_DIR / filename).resolve()
    if EMAIL_TEMPLATE_DIR.resolve() not in candidate.parents:
        raise ValueError("Template path escapes the email directory.")
    return candidate


def list_templates() -> list[str]:
    """Return the .html filenames in the email templates directory."""
    EMAIL_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        p.name for p in EMAIL_TEMPLATE_DIR.iterdir() if p.suffix == ".html"
    )


def read_template(filename: str) -> str:
    """Read a template's content (404-equivalent raises ValueError)."""
    path = _safe_path(filename)
    if not path.exists():
        raise FileNotFoundError("Template not found.")
    return path.read_text(encoding="utf-8")


def write_template(filename: str, content: str) -> str:
    """Write a template's content; returns the filename."""
    path = _safe_path(filename)
    EMAIL_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")
    return filename
