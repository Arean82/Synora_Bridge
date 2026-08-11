"""
INI configuration loader for Synora Bridge (Django backend).

Reads `backend/config.ini` (the single source of runtime configuration, as in
the original original app). Returns a cached ConfigParser instance; settings use
it directly with typed getters and safe fallbacks.

Also provides the shared read/write helpers used by the System Configuration
API (`GET/PUT /api/v1/config/`) and the `scripts/setup_db.py` bootstrap:
- `get_config_dict()`  — read the whole file as {section: {key: value}}
- `set_ini_value()`    — write one key, preserving comments/formatting
"""
import configparser
import re
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PATH = BACKEND_DIR / "config.ini"

# Keys whose change requires an application restart to take effect (core).
CORE_RESTART_KEYS = {
    "Server": {"host", "port", "timezone", "allowed_hosts", "environment", "debug"},
    "POSTGRES": {"host", "port", "database", "username", "password"},
    "SQLITE": {"path", "database"},
    "CELERY": {"broker_url", "result_backend", "always_eager"},
    "SECURITY": {"secret_key", "encryption_key"},
    # OTel initializes at startup — changes need a restart.
    "OPENTELEMETRY": {"enabled", "otlp_endpoint", "service_name"},
}


@lru_cache(maxsize=1)
def load_ini(path: Path | str | None = None) -> configparser.ConfigParser:
    """Load and cache the config.ini file (default: backend/config.ini).

    Uses interpolation=None (raw values) so passwords/URLs containing `%`
    parse correctly instead of raising InterpolationSyntaxError.
    """
    config = configparser.ConfigParser(interpolation=None)
    config.read(path or DEFAULT_PATH)
    return config


def get(path: Path | str | None = None) -> configparser.ConfigParser:
    """Typed-access helper entry point (kept for readability in settings)."""
    return load_ini(path)


def get_config_dict(path: Path | str | None = None) -> dict[str, dict[str, str]]:
    """Read the entire config file as {section: {key: value}}.

    Reads the file fresh (bypassing the lru_cache) so the System Configuration
    GUI always reflects the current on-disk state. Raw values (no `%`
    interpolation) so passwords/URLs with `%` are preserved verbatim.
    """
    target = Path(path) if path else DEFAULT_PATH
    config = configparser.ConfigParser(interpolation=None)
    config.read(target)
    return {
        section: {key: value for key, value in config.items(section)}
        for section in config.sections()
    }


def set_ini_value(path: Path | str, section: str, key: str, value: str) -> None:
    """Set `key = value` inside `[section]`, preserving comments/formatting.

    If the key already exists in the section its line is replaced in place;
    otherwise the key is appended to the section (creating it if missing).
    """
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines()
    section_header = f"[{section}]"
    in_section = False
    replaced = False
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped.lower() == section_header.lower()
        elif (
            in_section
            and not stripped.startswith(("#", ";"))
            and re.match(rf"^{re.escape(key)}\s*=", stripped, re.IGNORECASE)
        ):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}{key} = {value}")
            replaced = True
            continue
        out.append(line)

    if not replaced:
        if not any(l.strip().lower() == section_header.lower() for l in out):
            out.append("")
            out.append(section_header)
        out.append(f"{key} = {value}")

    target.write_text("\n".join(out) + "\n", encoding="utf-8")


def requires_restart(section: str, key: str) -> bool:
    """True if changing this key requires an app restart to take effect."""
    return key in CORE_RESTART_KEYS.get(section, set())
