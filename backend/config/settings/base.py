"""
Base settings shared by all environments.

Runtime configuration comes from `backend/config.ini` (via
`config.ini_config.load_ini()`), mirroring the original original app. Environment
variables act only as an optional override for secrets (SECRET_KEY,
ENCRYPTION_KEY) so credentials never need to live in the config file.
"""
import os
from pathlib import Path

from config.ini_config import load_ini

# Project root: backend/ (two levels up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load the runtime config file once (cached).
INI = load_ini()


def ini_get(section, key, fallback=""):
    """Typed helper: read a string from config.ini with fallback."""
    try:
        return INI.get(section, key).strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return fallback


def ini_bool(section, key, fallback=False):
    try:
        return INI.getboolean(section, key)
    except Exception:
        return fallback


def ini_int(section, key, fallback=0):
    try:
        return INI.getint(section, key)
    except Exception:
        return fallback


import configparser  # noqa: E402  (needed for exception classes above)

# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------
# Environment flag: development â†’ SQLite, production â†’ PostgreSQL
# (same semantics as the original original config.py).
ENVIRONMENT = ini_get("Server", "environment", "development").lower()

# Secret keys: prefer env, fall back to config.ini.
SECRET_KEY = (
    os.environ.get("DJANGO_SECRET_KEY")
    or ini_get("SECURITY", "secret_key")
    or "dev-insecure-change-me"
)
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY") or ini_get("SECURITY", "encryption_key")

DEBUG = ini_bool("Server", "debug", fallback=(ENVIRONMENT == "development"))

ALLOWED_HOSTS = [
    h.strip()
    for h in ini_get("SERVER", "allowed_hosts", "127.0.0.1,localhost").split(",")
    if h.strip()
]

# Application definition — modular apps registered per feature domain.
DJANGO_APPS = [
    "daphne",  # must come before django.contrib.staticfiles for ASGI serving
    # Jazzmin must precede django.contrib.admin so its templates override the
    # default admin chrome. (admin_black / admin_material are standalone full
    # admin skins, not Jazzmin dropdown themes — not installed; they would add
    # dead migrations and no working integration.)
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "channels",
    "django_celery_beat",
    "drf_spectacular",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.core",
    "apps.configs",
    "apps.connections",
    "apps.jobs",
    "apps.pull",
    "apps.realtime",
    "apps.observability",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serve /static/ under ASGI (daphne) — needed by DRF browsable API + admin.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — driven by [Server] environment:
#   development â†’ SQLite ([SQLITE] path/database)
#   production  â†’ PostgreSQL ([POSTGRES] host/port/database/username/password)
# ---------------------------------------------------------------------------
if ENVIRONMENT == "production":
    pool_max_age = ini_int("DatabasePool", "max_age_seconds", 60)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": ini_get("POSTGRES", "database", "bridge_db"),
            "USER": ini_get("POSTGRES", "username", "postgres"),
            "PASSWORD": ini_get("POSTGRES", "password", ""),
            "HOST": ini_get("POSTGRES", "host", "localhost"),
            "PORT": ini_get("POSTGRES", "port", "5432"),
            "CONN_MAX_AGE": pool_max_age,
        }
    }
else:
    sqlite_path = ini_get("SQLITE", "path", "instance")
    sqlite_db_name = ini_get("SQLITE", "database", "bridge_app.db")
    if not os.path.isabs(sqlite_path):
        sqlite_path = os.path.join(BASE_DIR.parent, sqlite_path)
    os.makedirs(sqlite_path, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(sqlite_path, sqlite_db_name),
        }
    }

# ---------------------------------------------------------------------------
# Production invariants (enforced regardless of which settings module loads)
# ---------------------------------------------------------------------------
if ENVIRONMENT == "production":
    if DEBUG:
        raise RuntimeError(
            "Production environment must not run with debug=true in config.ini."
        )
    if not SECRET_KEY or SECRET_KEY == "dev-insecure-change-me":
        raise RuntimeError("Production requires [SECURITY] secret_key.")
    if not ENCRYPTION_KEY:
        raise RuntimeError("Production requires [SECURITY] encryption_key.")
    if ini_bool("CELERY", "always_eager", fallback=False):
        raise RuntimeError("Production must not run Celery eagerly ([CELERY] always_eager = false).")

    # Hardened transport defaults for production.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS only over HTTPS; 31536000s = 1 year. Requires the reverse proxy to
    # set X-Forwarded-Proto (deploy/nginx.conf does).
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    # Development convenience: console email backend (no SMTP server needed).
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Redis / Memurai — channel layer + Celery broker.
# ---------------------------------------------------------------------------
REDIS_URL = ini_get("REDIS", "url", "redis://localhost:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = ini_get("CELERY", "broker_url", REDIS_URL)
CELERY_RESULT_BACKEND = ini_get("CELERY", "result_backend", "redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = ini_get("CELERY", "task_timezone", ini_get("Server", "timezone", "Asia/Kolkata"))
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ALWAYS_EAGER = ini_bool("CELERY", "always_eager", fallback=False)
CELERY_TASK_EAGER_PROPAGATES = True
# Worker scaling (#4) from config.ini [CELERY].
CELERY_WORKER_CONCURRENCY = ini_int("CELERY", "worker_concurrency", 4)
CELERY_WORKER_PREFETCH_MULTIPLIER = ini_int("CELERY", "worker_prefetch_multiplier", 4)
CELERY_TASK_ACKS_LATE = ini_bool("CELERY", "task_acks_late", False)
CELERY_TASK_SOFT_TIME_LIMIT = ini_int("CELERY", "task_soft_time_limit", 120)
CELERY_TASK_TIME_LIMIT = ini_int("CELERY", "task_time_limit", 180)

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    # The original original app had no user accounts on the management API; the
    # Nuxt frontend must be able to manage templates/jobs/connections without
    # a login flow. Pull endpoints enforce per-template bearer auth instead
    # (see apps.pull). Django admin remains session-guarded.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        # JSON-only for the API — the docs/exploration layer is Swagger UI +
        # Redoc + the Nuxt API-docs page (no DRF Browsable API exposed to
        # developers/users).
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

# drf-spectacular — generates the OpenAPI schema for hey-api / dart-dio clients.
SPECTACULAR_SETTINGS = {
    "TITLE": "Synora Bridge API",
    "DESCRIPTION": (
        "Universal API bridge: scheduled multi-source push, pull REST with "
        "dynamic OpenAPI specs, pull GraphQL with a dynamic Strawberry schema, "
        "and a Swagger-driven mock server."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Highest OpenAPI version drf-spectacular supports (3.0.3 default, 3.1.0
    # supported; 3.2.0 is NOT a drf-spectacular capability — the pull-endpoint
    # spec generator serves 3.2.0 separately, built from the OAS 3.2.0 spec).
    "OAS_VERSION": "3.1.0",
    # auth_type and spec_auth_type share one choices tuple; a single override
    # gives the shared set one stable name (drf-spectacular dedupes by content).
    "ENUM_NAME_OVERRIDES": {
        "ConnectionAuthTypeEnum": "apps.connections.models.Connection.AUTH_TYPES",
    },
}

# ---------------------------------------------------------------------------
# CORS (Nuxt frontend on a different origin during dev)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in ini_get("CORS", "allowed_origins", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Auth / users (simple token auth for API; session for admin)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Django admin theming (Jazzmin + Black/Material skins)
# ---------------------------------------------------------------------------
JAZZMIN_SETTINGS = {
    "site_title": "Synora Bridge Admin",
    "site_header": "Synora Bridge",
    "site_brand": "Synora Bridge",
    "welcome_sign": "Synora Bridge Administration",
    "copyright": "Synora Bridge",
    "search_model": ["configs.Template", "connections.Connection", "jobs.Job"],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    # Theme dropdown — Black + Material selectable from the admin UI.
    "show_ui_builder": True,
    "icons": {
        "configs.Template": "fas fa-sitemap",
        "connections.Connection": "fas fa-link",
        "jobs.Job": "fas fa-clock",
        "jobs.JobLog": "fas fa-list",
        "core.AuditLog": "fas fa-clipboard-list",
        "core.AppSetting": "fas fa-cog",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": False,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default",
    "dark_mode_theme": "darkly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

# ---------------------------------------------------------------------------
# Internationalization & timezone
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = ini_get("Server", "timezone", "Asia/Kolkata")

# Fail fast on an invalid [Server] timezone instead of silently falling back.
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: E402

try:
    ZoneInfo(TIME_ZONE)
except ZoneInfoNotFoundError:
    raise RuntimeError(
        f"[Server] timezone '{TIME_ZONE}' is not a valid IANA timezone. "
        "Example values: Asia/Kolkata, UTC, America/New_York. On Windows the "
        "tzdata package (in requirements.txt) provides the timezone database."
    ) from None

USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Compressed + hashed static files served by WhiteNoiseMiddleware (daphne/ASGI).
# Lenient subclass tolerates bundled JS referencing sourcemaps that don't ship
# with the package (admin-material's bootstrap bundle) — strips the reference
# instead of failing the whole collectstatic pass. Real files still hashed.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.storage.LenientManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Synora Bridge application settings (mirrors config.ini)
# ---------------------------------------------------------------------------
APP_TIMEZONE = TIME_ZONE
UI_DATE_FORMAT = ini_get("UI", "date_format", "DD/MM/YYYY HH:mm:ss")
LOG_DIR = BASE_DIR / ini_get("LOGGING", "log_dir", "logs")
LOG_ROTATION = ini_get("LOGGING", "rotation", "midnight")
LOG_BACKUP_COUNT = ini_int("LOGGING", "backup_count", 30)
RETRY_QUEUE_RETENTION_MINUTES = ini_int("RETRY_QUEUE", "retention_minutes", 60)
SWAGGER_REFRESH_INTERVAL = ini_int("SWAGGER", "refresh_interval", 1)
SWAGGER_REFRESH_UNIT = ini_get("SWAGGER", "refresh_unit", "hours")

# Email alerts (mirrors [EMAIL] section)
EMAIL_MODE = ini_get("EMAIL", "mode", "none").lower()  # none | local | smtp
EMAIL_SENDER = ini_get("EMAIL", "sender_email", "noreply@bridge.local")
EMAIL_RECIPIENTS = [
    e.strip() for e in ini_get("EMAIL", "recipient_emails", "").split(",") if e.strip()
]
EMAIL_SMTP_HOST = ini_get("EMAIL", "smtp_host", "smtp.gmail.com")
EMAIL_SMTP_PORT = ini_int("EMAIL", "smtp_port", 587)
EMAIL_SMTP_USER = ini_get("EMAIL", "smtp_user", "")
EMAIL_SMTP_PASSWORD = ini_get("EMAIL", "smtp_password", "")
EMAIL_THROTTLE_ENABLED = ini_bool("EMAIL", "throttle_enabled", False)
EMAIL_THROTTLE_MINUTES = ini_int("EMAIL", "throttle_minutes", 60)

# ---------------------------------------------------------------------------
# OpenTelemetry (config.ini [OPENTELEMETRY])
# ---------------------------------------------------------------------------
OTEL_ENABLED = ini_bool("OPENTELEMETRY", "enabled", False)
OTEL_EXPORTER_OTLP_ENDPOINT = ini_get("OPENTELEMETRY", "otlp_endpoint", "http://localhost:4318/v1/traces")
OTEL_SERVICE_NAME = ini_get("OPENTELEMETRY", "service_name", "synora-bridge")
OTEL_INSTRUMENT = {
    "django": ini_bool("OPENTELEMETRY", "instrument_django", True),
    "requests": ini_bool("OPENTELEMETRY", "instrument_requests", True),
    "celery": ini_bool("OPENTELEMETRY", "instrument_celery", True),
    "http": ini_bool("OPENTELEMETRY", "instrument_http", True),
}

# ---------------------------------------------------------------------------
# Rate limiting for pull endpoints (config.ini [RateLimit])
# ---------------------------------------------------------------------------
RATE_LIMIT_ENABLED = ini_bool("RateLimit", "enabled", True)
RATE_LIMIT_RATE = ini_get("RateLimit", "rate", "60")
RATE_LIMIT_PERIOD = ini_get("RateLimit", "period", "minute")
# django-ratelimit uses the cache backend for the in-memory/redis store.
RATELIMIT_USE_CACHE = "default"

# ---------------------------------------------------------------------------
# Pull response cache (config.ini [Cache])
# ---------------------------------------------------------------------------
PULL_CACHE_ENABLED = ini_bool("Cache", "enabled", True)
PULL_CACHE_TTL_SECONDS = ini_int("Cache", "default_ttl_seconds", 15)

# Redis-backed cache shared with the channel layer (unless disabled).
if PULL_CACHE_ENABLED:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

# ---------------------------------------------------------------------------
# Database pooling (config.ini [DatabasePool]) — CONN_MAX_AGE is applied in
# the DATABASES block above; PgBouncer config ships in deploy/pgbouncer.ini.
# ---------------------------------------------------------------------------
DATABASE_POOL_ENABLED = ini_bool("DatabasePool", "enabled", False)

# ---------------------------------------------------------------------------
# Reverse proxy (config.ini [ReverseProxy]) — nginx config ships in
# deploy/nginx.conf; the app only needs to trust the proxy headers.
# ---------------------------------------------------------------------------
REVERSE_PROXY_ENABLED = ini_bool("ReverseProxy", "enabled", False)
if REVERSE_PROXY_ENABLED and ENVIRONMENT == "production":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
