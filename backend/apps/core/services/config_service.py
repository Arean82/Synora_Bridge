"""
System Configuration service — read/write access to backend/config.ini.

Powers `GET/PUT /api/v1/config/` (the System Configuration GUI). Values are
typed (bool/int/str) so the frontend renders the right widget; writes are
validated (unknown sections/keys rejected) and applied without destroying
comments (set_ini_value). Reports which changed keys require a restart.

Faithful to the original original settings page semantics, minus its bugs:
- checkbox booleans default to false when absent (original parity)
- no `os.execl` self-restart; a `restart_required` flag is returned instead
"""
from config.ini_config import get_config_dict, requires_restart, set_ini_value
from zoneinfo import available_timezones


def _typed_value(value: str) -> bool | int | str:
    """Infer the runtime type of a config value for the UI widget."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return value


# Dropdown options per config key (rendered as <select> in the System
# Configuration GUI). Keys without options render as text/number/bool inputs.
DROPDOWN_OPTIONS = {
    "Server.environment": ["development", "production"],
    "Server.timezone": sorted(available_timezones()),
    "CELERY.task_timezone": sorted(available_timezones()),
    "UI.theme": ["default", "glass", "clay", "neobrut", "solid"],
    "UI.colormode": ["auto", "light", "dark"],
    "UI.layout": ["sidebar", "top"],
    "UI.date_format": ["DD/MM/YYYY HH:mm:ss", "MM/DD/YYYY HH:mm:ss", "YYYY-MM-DD HH:mm:ss"],
    "Logging.rotation": ["midnight", "daily", "weekly", "hourly", "monthly"],
    "Swagger.refresh_unit": ["minutes", "hours", "days"],
    "Email.mode": ["none", "local", "smtp"],
    "RateLimit.period": ["second", "minute", "hour", "day"],
    # All boolean keys get string options ("true"/"false") so the GUI dropdown
    # matches the stored string value (a `:value="true"` select wouldn't).
    "Server.debug": ["true", "false"],
    "POSTGRES.enabled": ["true", "false"],
    "SQLITE.enabled": ["true", "false"],
    "OPENTELEMETRY.enabled": ["true", "false"],
    "OPENTELEMETRY.instrument_django": ["true", "false"],
    "OPENTELEMETRY.instrument_requests": ["true", "false"],
    "OPENTELEMETRY.instrument_celery": ["true", "false"],
    "OPENTELEMETRY.instrument_http": ["true", "false"],
    "RateLimit.enabled": ["true", "false"],
    "Cache.enabled": ["true", "false"],
    "DatabasePool.enabled": ["true", "false"],
    "ReverseProxy.enabled": ["true", "false"],
    "CELERY.always_eager": ["true", "false"],
    "CELERY.task_acks_late": ["true", "false"],
    "Email.throttle_enabled": ["true", "false"],
}


def get_full_config(path=None) -> dict:
    """Return the whole config as {section: {key: {value, type, options?}}}."""
    raw = get_config_dict(path)
    result: dict[str, dict[str, dict]] = {}
    for section, keys in raw.items():
        result[section] = {}
        for key, val in keys.items():
            entry: dict = {"value": val, "type": type(_typed_value(val)).__name__}
            options = DROPDOWN_OPTIONS.get(f"{section}.{key}")
            if options:
                entry["options"] = options
            result[section][key] = entry
    return result


def update_config(changes: dict, path=None) -> dict:
    """Apply validated section/key changes to config.ini.

    changes: {section: {key: value}} (values are strings).
    Returns {updated: [...], restart_required: bool, restart_keys: [...]}.
    Raises ValueError on unknown sections/keys (no silent creation of junk).

    Database-engine handling (production selector = per-section enabled flags):
    - Exactly one database stays enabled. Touching either [POSTGRES] enabled or
      [SQLITE] enabled pins its value and sets the other to the complement:
      disabling SQLite therefore ENABLES PostgreSQL (and vice versa) — the
      production invariants refuse to boot with both (or neither) enabled.
    - PostgreSQL gate: switching the effective engine TO PostgreSQL (whether by
      enabling POSTGRES or by disabling SQLite) requires a verified connection.
      On failure the switch is NOT persisted — SQLite stays enabled and the
      response carries `db_fallback` so the UI can tell the user why.
    """
    current = get_config_dict(path)
    updated: list[str] = []
    restart_keys: list[str] = []
    db_fallback: dict | None = None

    changes = dict(changes or {})

    # --- Database-engine selector: exactly one database stays enabled ---
    pg_section = dict(changes.get("POSTGRES", {}) or {})
    sq_section = dict(changes.get("SQLITE", {}) or {})
    pg_toggle = pg_section.get("enabled")
    sq_toggle = sq_section.get("enabled")
    pg_already_on = str(current.get("POSTGRES", {}).get("enabled", "false")).lower() == "true"
    if pg_toggle is not None or sq_toggle is not None:
        # Effective target: a pinned POSTGRES.enabled wins; otherwise it is the
        # complement of the payload's SQLITE.enabled.
        if pg_toggle is not None:
            want_pg = str(pg_toggle).lower() == "true"
        else:
            want_pg = str(sq_toggle).lower() != "true"

        if want_pg and not pg_already_on:
            # Enabling PostgreSQL (directly, or by disabling SQLite) requires a
            # verified connection.
            merged = dict(current.get("POSTGRES", {}))
            for k, v in pg_section.items():
                merged[k] = str(v)
            ok, err = verify_postgres_connection(
                merged.get("host", "localhost"),
                merged.get("port", "5432"),
                merged.get("database", "bridge_db"),
                merged.get("username", "postgres"),
                merged.get("password", ""),
            )
            if not ok:
                # Not verified: drop the PG switch and keep SQLite enabled (the
                # checkbox-parity defaulting below would otherwise flip it to
                # false and disable every database).
                changes.pop("POSTGRES", None)
                changes.setdefault("SQLITE", {})["enabled"] = "true"
                db_fallback = {
                    "requested": "postgresql",
                    "applied": "sqlite",
                    "reason": f"PostgreSQL connection not verified: {err}",
                }
            else:
                changes.setdefault("POSTGRES", {})["enabled"] = "true"
                changes.setdefault("SQLITE", {})["enabled"] = "false"
        elif want_pg:
            # PostgreSQL already enabled — keep it and switch SQLite off.
            changes.setdefault("SQLITE", {})["enabled"] = "false"
        else:
            # SQLite is the target — switch PostgreSQL off (no gate needed).
            changes.setdefault("SQLITE", {})["enabled"] = "true"
            changes.setdefault("POSTGRES", {})["enabled"] = "false"

    for section, keys in (changes or {}).items():
        if section not in current:
            raise ValueError(f"Unknown config section: {section}")
        for key, value in keys.items():
            if key not in current[section]:
                raise ValueError(f"Unknown config key: {section}.{key}")
            new_value = str(value)
            if new_value != current[section][key]:
                set_ini_value(path or _default_path(), section, key, new_value)
                updated.append(f"{section}.{key}")
                if requires_restart(section, key):
                    restart_keys.append(f"{section}.{key}")

    # Checkbox parity: boolean keys not present in the payload default to false.
    raw = get_config_dict(path)
    for section, keys in raw.items():
        for key, val in keys.items():
            if isinstance(_typed_value(val), bool) and section in (changes or {}):
                if key not in (changes or {}).get(section, {}):
                    set_ini_value(path or _default_path(), section, key, "false")
                    updated.append(f"{section}.{key}")

    result: dict = {
        "updated": sorted(set(updated)),
        "restart_required": bool(restart_keys),
        "restart_keys": sorted(set(restart_keys)),
    }
    if db_fallback:
        result["db_fallback"] = db_fallback
    return result


def verify_postgres_connection(host, port, database, username, password, timeout=5):
    """Attempt a real connection to PostgreSQL. Returns (ok, error).

    Stateless: never writes to config.ini, never logs credentials. A short
    connect_timeout keeps the UI responsive when the host is unreachable.
    """
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=host or "localhost",
            port=port or "5432",
            dbname=database or "bridge_db",
            user=username or "postgres",
            password=password or "",
            connect_timeout=timeout,
        )
        conn.close()
        return True, ""
    except Exception as exc:  # noqa: BLE001 — surface any connection error to the UI
        return False, str(exc)


def _default_path():
    from config.ini_config import DEFAULT_PATH

    return DEFAULT_PATH
