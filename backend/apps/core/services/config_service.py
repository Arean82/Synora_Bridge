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
    """
    current = get_config_dict(path)
    updated: list[str] = []
    restart_keys: list[str] = []

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

    return {
        "updated": sorted(set(updated)),
        "restart_required": bool(restart_keys),
        "restart_keys": sorted(set(restart_keys)),
    }


def _default_path():
    from config.ini_config import DEFAULT_PATH

    return DEFAULT_PATH
