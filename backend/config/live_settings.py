"""
Live settings — values that apply WITHOUT a backend restart.

`django.conf.settings` freezes every value at import (LazySettings caches each
attribute and base.py materializes constants), so runtime-consumed values are
read here straight from config.ini with a short TTL cache. Saving one of these
in the System Configuration GUI takes effect immediately — no restart.

Truly immutable wiring (database engine/creds, SECURITY keys, environment,
debug, timezone, allowed_hosts, Celery broker, OTel, ReverseProxy) stays in
`django.conf.settings` and is handled by the one-click Restart button
(`POST /api/v1/config/restart/`).
"""
import configparser
import time

from config.ini_config import DEFAULT_PATH, find_section

# Short TTL so a burst of requests doesn't reparse config.ini every time,
# while a config save still becomes visible within ~1s.
_CACHE_TTL_SECONDS = 1.0
_cache: dict = {"at": 0.0, "config": None}


def clear_cache() -> None:
    """Drop the cached config (tests / after an explicit save)."""
    _cache["at"] = 0.0
    _cache["config"] = None


def _read():
    now = time.monotonic()
    if _cache["config"] is None or now - _cache["at"] > _CACHE_TTL_SECONDS:
        config = configparser.ConfigParser(interpolation=None)
        config.read(DEFAULT_PATH)
        _cache["config"] = config
        _cache["at"] = now
    return _cache["config"]


def _sec(section):
    """Case-insensitive section lookup (config.ini mixes [Email]/[RateLimit]/...)."""
    return find_section(_read(), section)


def _str(section, key, fallback=""):
    sec = _sec(section)
    if sec is None or key not in sec:
        return fallback
    return sec[key].strip()


def _bool(section, key, fallback=False):
    sec = _sec(section)
    if sec is None:
        return fallback
    try:
        return sec.getboolean(key)
    except Exception:  # noqa: BLE001 — any parse problem falls back
        return fallback


def _int(section, key, fallback=0):
    sec = _sec(section)
    if sec is None:
        return fallback
    try:
        return sec.getint(key)
    except Exception:  # noqa: BLE001
        return fallback


def _list(section, key, fallback):
    value = _str(section, key, "")
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items if items else list(fallback)


class LiveList(list):
    """A list whose contents are re-read from config.ini on every access.

    corsheaders iterates/contains this object per request, so changing
    `[CORS] allowed_origins` applies immediately — no restart, no middleware
    swap. (The settings attribute itself is frozen by Django's LazySettings,
    but its METHODS are live.)
    """

    def __init__(self, section, key, fallback):
        super().__init__()
        self._section = section
        self._key = key
        self._fallback = list(fallback)

    def _current(self):
        return _list(self._section, self._key, self._fallback)

    def __iter__(self):
        return iter(self._current())

    def __contains__(self, item):
        return item in self._current()

    def __len__(self):
        return len(self._current())

    def __getitem__(self, index):
        return self._current()[index]

    def __bool__(self):
        return bool(self._current())

    def __repr__(self):
        return repr(self._current())


def live_list(section, key, fallback):
    """Build a LiveList for a comma-separated config key."""
    return LiveList(section, key, fallback)


class _Live:
    """Runtime-consumed settings namespace (read live, apply without restart)."""

    # --- CORS (consumed by corsheaders per request) ---
    @property
    def CORS_ALLOWED_ORIGINS(self):
        return live_list("CORS", "allowed_origins", ["http://localhost:3000", "http://127.0.0.1:3000"])

    # --- Email alerts (consumed by apps.core.services.email_service) ---
    @property
    def EMAIL_MODE(self):
        return _str("EMAIL", "mode", "none").lower()

    @property
    def EMAIL_SENDER(self):
        return _str("EMAIL", "sender_email", "noreply@bridge.local")

    @property
    def EMAIL_RECIPIENTS(self):
        return _list("EMAIL", "recipient_emails", [])

    @property
    def EMAIL_THROTTLE_ENABLED(self):
        return _bool("EMAIL", "throttle_enabled", False)

    @property
    def EMAIL_THROTTLE_MINUTES(self):
        return _int("EMAIL", "throttle_minutes", 60)

    # --- Rate limiting (consumed by apps.pull.views) ---
    @property
    def RATE_LIMIT_ENABLED(self):
        return _bool("RateLimit", "enabled", True)

    @property
    def RATE_LIMIT_RATE(self):
        return _str("RateLimit", "rate", "60")

    @property
    def RATE_LIMIT_PERIOD(self):
        return _str("RateLimit", "period", "minute")

    # --- Pull response cache (consumed by apps.pull.views) ---
    @property
    def PULL_CACHE_ENABLED(self):
        return _bool("Cache", "enabled", True)

    @property
    def PULL_CACHE_TTL_SECONDS(self):
        return _int("Cache", "default_ttl_seconds", 15)

    # --- Retry queue (consumed by apps.jobs.tasks.cleanup_failed_payloads) ---
    @property
    def RETRY_QUEUE_RETENTION_MINUTES(self):
        return _int("RETRY_QUEUE", "retention_minutes", 60)


live = _Live()
