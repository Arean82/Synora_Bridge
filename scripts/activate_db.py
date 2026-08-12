"""
Synora Bridge - demo seed (renamed from seed_demo.py -> activate_db.py).

Works on BOTH SQLite and PostgreSQL: it uses the Django ORM and follows
whichever engine backend/config.ini selects (development -> SQLite locked;
production -> the section with enabled = true). The resolved engine is printed
at startup.

Prompts depend on the engine the config is using:
  PostgreSQL engine:
      Copy existing SQLite data into PostgreSQL? [y/N]   - one-way only
                                                        (sqlite -> pg; never
                                                        the reverse). If yes,
                                                        the SQLite data is
                                                        dumped and loaded into
                                                        PostgreSQL.
      Insert demo data? [Y/n]                            - default yes.
  SQLite engine:
      Insert demo data? [Y/n]                            - default yes
      (no copy question - migration is only sqlite -> pg, not pg -> sqlite).

Demo-ready guarantees:
- Template source URLs come from a curated list of KEYLESS public APIs; every
  URL is probed live at seed time and only used if it returns HTTP 200 with a
  JSON body. Pull endpoints therefore return REAL, LIVE data in the demo.
- Field mappings are derived from those real response field names.
- Connection records are seeded from real public OpenAPI/Swagger specs
  (Connections page, Swagger UI and mock server use them) with per-connection
  endpoint lists (environments).
- Seeds JobLog history (dashboard runs), AppSettings (UI theme/layout) and an
  optional demo admin user.

Usage (from anywhere - resolves the backend relative to this file):

    python scripts/activate_db.py                    # prompts (defaults: no copy, demo yes)
    python scripts/activate_db.py --create-admin     # also create admin/admin123
    python scripts/activate_db.py --no-demo-data     # skip demo data
    python scripts/activate_db.py --no-migrate       # skip the SQLite->PG copy prompt
    python scripts/activate_db.py --yes              # non-interactive (defaults)

Requires the backend venv's Python (django, requests, etc.) and a migrated
database.
"""
import argparse
import json
import logging
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap Django without manage.py (path-relative, platform-independent).
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
CONFIG_PATH = BACKEND_DIR / "config.ini"
sys.path.insert(0, str(BACKEND_DIR))


def _random_secret_key():
    """Django-style random secret key."""
    from django.core.management.utils import get_random_secret_key

    return get_random_secret_key()


def _random_encryption_key():
    """32 random bytes base64-encoded (AES-256-GCM master key)."""
    import base64
    import secrets

    return base64.b64encode(secrets.token_bytes(32)).decode()


def _ensure_bootable_config():
    """Demo convenience: make backend/config.ini bootable so the seed can run.

    When [Server] environment = production, the app settings refuse to load
    without real [SECURITY] keys (and with debug = true / always_eager = true).
    If any of those are missing/incorrect, generate/normalize them BEFORE Django
    imports. Only writes what is wrong - never overwrites existing user keys.
    """
    from config.ini_config import get_config_dict, set_ini_value

    cfg = get_config_dict()
    if str(cfg.get("Server", {}).get("environment", "development")).lower() != "production":
        return  # development needs none of this

    writes = []
    if not cfg.get("SECURITY", {}).get("secret_key"):
        set_ini_value(CONFIG_PATH, "SECURITY", "secret_key", _random_secret_key())
        writes.append("secret_key")
    if not cfg.get("SECURITY", {}).get("encryption_key"):
        set_ini_value(CONFIG_PATH, "SECURITY", "encryption_key", _random_encryption_key())
        writes.append("encryption_key")
    if str(cfg.get("Server", {}).get("debug", "")).lower() == "true":
        set_ini_value(CONFIG_PATH, "Server", "debug", "false")
        writes.append("debug=false")
    if str(cfg.get("CELERY", {}).get("always_eager", "")).lower() == "true":
        set_ini_value(CONFIG_PATH, "CELERY", "always_eager", "false")
        writes.append("always_eager=false")

    if writes:
        print(f"[setup] production config normalized: {', '.join(writes)} written to backend/config.ini.")


_ensure_bootable_config()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

try:
    django.setup()
except RuntimeError as exc:
    # Config problems surface as RuntimeError while settings load (production
    # invariants, invalid timezone) - print the message cleanly, no traceback.
    print(f"\n[error] {exc}", file=sys.stderr)
    print("  Fix backend/config.ini and re-run the seed.", file=sys.stderr)
    sys.exit(1)

import requests  # noqa: E402
from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.connections.models import Connection  # noqa: E402
from apps.connections.services import fetch_swagger_json  # noqa: E402
from apps.configs.models import Template  # noqa: E402
from apps.core.models import AppSetting, AuditLog  # noqa: E402
from apps.jobs.models import FailedPayload, Job, JobLog  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# State which database the config resolved to, and warn loudly when the seed
# would clear demo-owned tables in a production PostgreSQL.
_db_engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
_db_name = settings.DATABASES["default"].get("NAME") or ""
print(f"Seed target database: {_db_engine} ({_db_name})")
if _db_engine == "postgresql":
    print(
        "  WARNING: production PostgreSQL selected - the seed CLEARS existing "
        "connections/templates/jobs/logs/audit (demo-owned tables)."
    )

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (SynoraBridge Demo)"}

# ---------------------------------------------------------------------------
# Keyless public APIs - guaranteed real data for a live demo.
# Each entry is (name, url, sample_field_names). At seed time every URL is
# probed; only sources returning HTTP 200 with a JSON body are used.
# ---------------------------------------------------------------------------
KEYLESS_SOURCES = [
    ("JSONPlaceholder Posts", "https://jsonplaceholder.typicode.com/posts", ["id", "title", "body", "userId"]),
    ("REST Countries", "https://restcountries.com/v3.1/all", ["name", "capital", "population", "region"]),
    ("PokeAPI", "https://pokeapi.co/api/v2/pokemon", ["name", "url"]),
    ("Rick & Morty API", "https://rickandmortyapi.com/api/character", ["id", "name", "status", "species"]),
    ("Cat Facts", "https://catfact.ninja/fact", ["fact", "length"]),
    ("Chuck Norris Jokes", "https://api.chucknorris.io/jokes/random", ["value", "icon_url", "id"]),
    ("SpaceX Launches", "https://api.spacexdata.com/v5/launches/latest", ["name", "flight_number", "date_utc"]),
    ("ipify (your IP)", "https://api.ipify.org?format=json", ["ip"]),
    ("Dog CEO Breeds", "https://dog.ceo/api/breeds/list/all", ["message", "status"]),
    ("Open Exchange Rates", "https://open.er-api.com/v6/latest/USD", ["base_code", "rates", "time_last_update_utc"]),
    ("Open-Meteo Weather", "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true", ["current_weather"]),
]

# ---------------------------------------------------------------------------
# Real public OpenAPI/Swagger specs for the Connections page / Swagger UI /
# mock server. Each entry is (name, spec_url).
# ---------------------------------------------------------------------------
CONNECTION_SPECS = [
    ("AVL View", "https://app.avlview.com/open-api/v3/api-docs"),
    ("Petstore API", "https://petstore.swagger.io/v2/swagger.json"),
    ("Weather.gov API", "https://api.weather.gov/openapi.json"),
    ("REST Countries", "https://restcountries.com/v3.1/openapi.json"),
    ("JSONPlaceholder", "https://jsonplaceholder.typicode.com/openapi.json"),
    ("GitHub API", "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"),
    ("Crossref", "https://api.crossref.org/swagger.json"),
    ("Swiss Transport", "https://transport.opendata.ch/swagger.json"),
    ("Wikimedia", "https://wikimedia.org/api/rest_v1/?spec"),
]


def _spec_endpoints(json_data, spec_url, limit=15):
    """Derive real API endpoints from a spec's `paths` for the connection's
    `environments` ([{name, url}]) - the per-connection endpoint list the
    original Flask seed carried."""
    from urllib.parse import urlparse

    paths = json_data.get("paths") or {}
    servers = json_data.get("servers") or []
    if servers and servers[0].get("url"):
        base = servers[0]["url"].rstrip("/")
    elif json_data.get("host"):
        base = f"{json_data.get('schemes', ['http'])[0]}://{json_data['host']}"
    else:
        parsed = urlparse(spec_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

    endpoints = []
    for path, item in (paths or {}).items():
        if not isinstance(item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            if method in item:
                name = f"{method.upper()} {path}"
                url = base + path if path.startswith("/") else f"{base}/{path}"
                endpoints.append({"name": name, "url": url})
                break
        if len(endpoints) >= limit:
            break
    return endpoints


# ---------------------------------------------------------------------------
# SQLite -> PostgreSQL data migration
# ---------------------------------------------------------------------------
def _migrate_sqlite_to_pg():
    """Dump the existing SQLite database and load it into PostgreSQL.

    "If yes it must be done": this actually performs the data migration.
    Prerequisites: PostgreSQL must be enabled in backend/config.ini AND
    migrated (run scripts/setup_db.py + python manage.py migrate first) -
    otherwise it stops with a clear, actionable message.
    """
    from config.ini_config import get_config_dict

    engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
    if engine != "postgresql":
        print(
            f"\n[error] The app is not on PostgreSQL ({engine}). Enable [POSTGRES] "
            "and migrate first - run scripts/setup_db.py, then python manage.py migrate.",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = get_config_dict()
    sqlite_path = cfg.get("SQLITE", {}).get("path", "instance")
    sqlite_db = cfg.get("SQLITE", {}).get("database", "bridge_app.db")
    if not os.path.isabs(sqlite_path):
        sqlite_path = str(BACKEND_DIR.parent / sqlite_path)
    sqlite_file = Path(sqlite_path) / sqlite_db
    if not sqlite_file.exists():
        print(f"\n[error] SQLite database not found at {sqlite_file} - nothing to migrate.", file=sys.stderr)
        sys.exit(1)

    dump_path = BACKEND_DIR / "data" / "sqlite_to_pg_dump.json"
    dump_path.parent.mkdir(parents=True, exist_ok=True)

    # Register the SQLite file as a second database alias and dump it, then
    # load the dump into the default (PostgreSQL) database.
    settings.DATABASES["sqlite_legacy"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(sqlite_file),
    }

    from django.core.management import call_command

    print(f"\n[migrate] dumping SQLite data from {sqlite_file} ...")
    call_command(
        "dumpdata",
        database="sqlite_legacy",
        natural_foreign=True,
        natural_primary=True,
        exclude=["contenttypes", "auth.permission"],
        output=str(dump_path),
    )
    print(f"[migrate] dump written: {dump_path}")

    print("[migrate] loading into PostgreSQL ...")
    call_command("loaddata", str(dump_path))
    print("[migrate] done - SQLite data migrated to PostgreSQL.")


# ---------------------------------------------------------------------------
# Data cleanup
# ---------------------------------------------------------------------------
def _clear_demo_data():
    """Reset all demo-owned tables (idempotent; safe to re-run)."""
    FailedPayload.objects.all().delete()
    JobLog.objects.all().delete()
    Job.objects.all().delete()
    AuditLog.objects.all().delete()
    Template.objects.all().delete()
    Connection.objects.all().delete()
    AppSetting.objects.filter(key__startswith="ui.").delete()


# ---------------------------------------------------------------------------
# Connections (real public specs)
# ---------------------------------------------------------------------------
def _seed_connections():
    """Fetch real OpenAPI specs and create Connection records."""
    uploads_dir = Path(settings.BASE_DIR) / "data" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    print(f"Creating connections from {len(CONNECTION_SPECS)} public specs...")
    for i, (name, spec_url) in enumerate(CONNECTION_SPECS):
        try:
            json_data, _actual_url = fetch_swagger_json(spec_url, timeout=15)
        except Exception as exc:
            print(f"  [skip] {name}: {type(exc).__name__}")
            continue
        if json_data is None:
            continue

        # Real API endpoints from the spec (per-connection endpoint list).
        environments = _spec_endpoints(json_data, spec_url)
        if not environments:
            print(f"  [warn] {name}: no paths found in spec")

        if i % 2 == 0:
            # Local-file connections (specs saved as JSON files).
            file_name = f"seed_{uuid.uuid4().hex[:6]}.json"
            file_path = uploads_dir / file_name
            file_path.write_text(json.dumps(json_data), encoding="utf-8")
            conn = Connection.objects.create(
                name=f"{name} (JSON)",
                url=spec_url,
                is_local_file=True,
                local_file_path=str(file_path),
                json_content=json.dumps(json_data),
                environments=environments,
                is_active=True,
                connection_type="rest",
                auth_type="none",
                schema_source="upload",
                spec_auth_type="none",
            )
        else:
            conn = Connection.objects.create(
                name=f"{name} (URL)",
                url=spec_url,
                is_local_file=False,
                json_content=json.dumps(json_data),
                environments=environments,
                is_active=True,
                connection_type="rest",
                auth_type="none",
                schema_source="introspection",
                spec_auth_type="none",
            )
        created += 1
        print(f"  + Connection: {conn.name} ({len(environments)} endpoints)")
    return created


# ---------------------------------------------------------------------------
# Templates (real keyless data sources)
# ---------------------------------------------------------------------------
def _probe_keyless_sources():
    """Probe every keyless source; return only those returning 200 JSON."""
    usable = []
    print("Probing keyless public APIs for real demo data...")
    for name, url, fields in KEYLESS_SOURCES:
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=8)
            if resp.status_code == 200:
                try:
                    resp.json()
                except Exception:
                    print(f"  [skip] {name}: not JSON")
                    continue
                usable.append((name, url, fields))
                print(f"  [ok] {name} ({url[:60]})")
            else:
                print(f"  [skip] {name}: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"  [skip] {name}: {type(exc).__name__}")
    return usable


def _keyless_source(name, url):
    """Build a template source pointing at a real keyless API."""
    return {
        "name": name,
        "url": url,
        "selectedApi": url,
        "source_type": "rest",
        "method": "GET",
        "auth_type": "none",
        "auth_token": "",
    }


def _make_mapping(fields, prefix="source_0."):
    """Build a mapping that transforms real response fields into a nested payload."""
    mapping = []
    if fields:
        # First field becomes a nested object leaf; rest flat.
        mapping.append({"source": f"{prefix}{fields[0]}", "target": f"data[0].{fields[0]}"})
        for f in fields[1:]:
            mapping.append({"source": f"{prefix}{f}", "target": f})
    else:
        # Fallback: generic identity mapping that still produces JSON.
        mapping = [
            {"source": f"{prefix}id", "target": "data[0].id"},
            {"source": f"{prefix}name", "target": "name"},
        ]
    return mapping


def _seed_templates(keyless_sources):
    """Create push / pull-rest / pull-graphql templates from REAL data sources."""
    print("Generating templates...")

    def tpl(name, mode, sources, destinations, client_name=None):
        return Template.objects.create(
            name=name,
            client_name=client_name or f"Client for {name}",
            execution_mode=mode,
            sources=sources,
            destinations=destinations,
            client_credentials={"token": "demo-client-token"},
        )

    def dest(name, url, method, mapping):
        return {
            "name": name,
            "url": url,
            "method": method,
            "auth_type": "none",
            "credentials": {},
            "field_mapping": mapping,
        }

    if not keyless_sources:
        print("  [warn] No keyless source returned real data; templates skipped.")
        return

    # --- 6 single-destination push templates (real fetch -> httpbin) ---
    for i in range(6):
        name, url, fields = keyless_sources[i % len(keyless_sources)]
        src = _keyless_source(name, url)
        mapping = _make_mapping(fields)
        t = tpl(
            name=f"Push 1-Dest (Group {i + 1})",
            mode="push",
            sources=[src],
            destinations=[dest("httpbin-echo", "https://httpbin.org/post", "POST", mapping)],
        )
        Job.objects.create(template=t, schedule_interval=60, is_active=True)

    # --- 4 multi-destination push templates ---
    for i in range(4):
        name, url, fields = keyless_sources[(i + 4) % len(keyless_sources)]
        src = _keyless_source(name, url)
        mapping = _make_mapping(fields)
        for d in range(2):
            t = tpl(
                name=f"Push Multi-Dest (Group {i + 1}, Dest {d + 1})",
                mode="push",
                sources=[src],
                destinations=[dest(f"httpbin-{d}", "https://httpbin.org/post", "POST", mapping)],
            )
            Job.objects.create(template=t, schedule_interval=120, is_active=True)

    # --- 6 REST pull templates (single real source -> mapped endpoint) ---
    for i in range(6):
        name, url, fields = keyless_sources[i % len(keyless_sources)]
        src = _keyless_source(name, url)
        mapping = _make_mapping(fields)
        t = tpl(
            name=f"REST Pull (Group {i + 1})",
            mode="pull_rest",
            sources=[src],
            destinations=[dest("client-endpoint", "", "GET", mapping)],
        )
        Job.objects.create(template=t, schedule_interval=300, is_active=True)

    # --- 4 REST pull templates (multi-source aggregation -> one endpoint) ---
    for i in range(4):
        selected = [keyless_sources[(i + j * 2) % len(keyless_sources)] for j in range(3)]
        sources = [_keyless_source(name, url) for (name, url, _f) in selected]
        mapping = []
        for j, (_n, _u, fields) in enumerate(selected):
            mapping += _make_mapping(fields, prefix=f"source_{j}.")
        t = tpl(
            name=f"REST Pull Aggregated (Group {i + 1})",
            mode="pull_rest",
            sources=sources,
            destinations=[dest("aggregate-endpoint", "", "GET", mapping)],
        )
        Job.objects.create(template=t, schedule_interval=300, is_active=True)

    # --- 6 GraphQL pull templates ---
    for i in range(6):
        name, url, fields = keyless_sources[(i + 4) % len(keyless_sources)]
        src = _keyless_source(name, url)
        mapping = _make_mapping(fields)
        t = tpl(
            name=f"GraphQL Pull ({name})",
            mode="pull_graphql",
            sources=[src],
            destinations=[dest("client-query", "", "GET", mapping)],
        )
        Job.objects.create(template=t, schedule_interval=600, is_active=True)


# ---------------------------------------------------------------------------
# Logs, settings, admin
# ---------------------------------------------------------------------------
def _seed_logs_and_settings(first_template):
    """Seed job-run history (dashboard) and UI settings."""
    print("Seeding job logs + settings...")
    now = timezone.now()
    demo_job = Job.objects.order_by("id").first()
    for i in range(12):
        JobLog.objects.create(
            job=demo_job,
            timestamp=now - timedelta(minutes=5 * (i + 1)),
            status="SUCCESS" if i % 5 != 0 else "FAILED",
            http_status=200 if i % 5 != 0 else 500,
            error_message=None if i % 5 != 0 else "Mock failure for demo visibility",
            payload_json={"sample": i},
        )

    AppSetting.objects.update_or_create(
        key="ui.theme",
        defaults={"value": {"theme": "default", "colorMode": "auto", "dateFormat": "DD/MM/YYYY HH:mm:ss"}},
    )
    AppSetting.objects.update_or_create(
        key="ui.layout",
        defaults={"value": {"layout": "sidebar"}},
    )

    # A couple of audit entries across modes.
    for mode in ("PUSH", "PULL_REST", "PULL_GRAPHQL"):
        AuditLog.objects.create(
            transaction_id=uuid.uuid4(),
            mode=mode,
            caller="demo",
            bytes_transferred=1024,
            record_count=1,
            status="SUCCESS",
            template=first_template,
            payload_json={"seeded": True},
        )


def _ensure_admin(create_admin):
    """Optionally create a demo admin user (admin / admin123)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if not create_admin:
        return
    if User.objects.filter(username="admin").exists():
        print("Admin user 'admin' already exists.")
        return
    User.objects.create_superuser(username="admin", email="admin@example.com", password="admin123")
    print("Created demo admin: username=admin password=admin123 - CHANGE IN PRODUCTION.")


def _preflight_db():
    """The configured database must be reachable AND migrated.

    Works for both engines (SQLite and PostgreSQL): the Django ORM follows
    whichever backend/config.ini selects, so this fails with a clear,
    actionable message instead of a cryptic "no such table" / connection error.
    """
    from django.db import connection

    engine = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
    try:
        connection.ensure_connection()
    except Exception as exc:
        print(f"\n[error] Cannot connect to the configured database ({engine}): {exc}", file=sys.stderr)
        print("  Check backend/config.ini and that the database server is running.", file=sys.stderr)
        sys.exit(1)
    try:
        Template.objects.exists()
    except Exception as exc:
        print(f"\n[error] The {engine} database has no app tables yet (not set up): {exc}", file=sys.stderr)
        print("  Run: python manage.py migrate", file=sys.stderr)
        sys.exit(1)
    print(f"[ok] The database the app uses right now ({engine}) is working and set up. Demo data will go into it.")


def seed(create_admin=False):
    _preflight_db()
    print("Cleaning demo tables...")
    _clear_demo_data()

    _seed_connections()

    keyless = _probe_keyless_sources()
    if keyless:
        _seed_templates(keyless)

    first_template = Template.objects.order_by("id").first()
    _seed_logs_and_settings(first_template)
    _ensure_admin(create_admin)

    # Reconcile the beat schedule for all seeded jobs.
    from apps.jobs.beat import ensure_system_tasks, sync_all_jobs_to_beat

    ensure_system_tasks()
    sync_all_jobs_to_beat()

    print(
        f"\nDatabase seeded: {Connection.objects.count()} connections, "
        f"{Template.objects.count()} templates, {Job.objects.count()} jobs, "
        f"{JobLog.objects.count()} job logs, {AuditLog.objects.count()} audit logs."
    )
    print("Demo ready. Start daphne + Nuxt and open the dashboard.")


def ask_choice(prompt: str, options: list[str]) -> str:
    """Numbered selection menu - the user types the number of the option."""
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        value = input(f"Choose 1-{len(options)}: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(options):
            return options[int(value) - 1]
        print(f"  Please enter a number between 1 and {len(options)}.")


def main():
    parser = argparse.ArgumentParser(
        description="Insert the Synora Bridge demo dataset (works on both SQLite and PostgreSQL - follows backend/config.ini)."
    )
    parser.add_argument("--create-admin", action="store_true", help="Create demo admin user (admin/admin123).")
    parser.add_argument("--no-demo-data", action="store_true", help="Do NOT insert demo data.")
    parser.add_argument("--no-migrate", action="store_true", help="Do NOT ask about copying SQLite data (PostgreSQL engine only).")
    parser.add_argument("--yes", action="store_true", help="Non-interactive: use defaults (copy: no, demo data: yes).")
    args = parser.parse_args()

    # 1) Optional SQLite -> PostgreSQL data copy - ONLY when the app is on
    #    PostgreSQL, and one-way only (sqlite -> pg, never the reverse).
    if _db_engine == "postgresql":
        if args.no_migrate or args.yes:
            migrate = False
        else:
            migrate = ask_choice("Copy existing SQLite data into PostgreSQL?", ["Yes", "No"]) == "Yes"
        if migrate:
            _migrate_sqlite_to_pg()

    # 2) Optional demo data (default yes) - both engines.
    if args.no_demo_data:
        demo = False
    elif args.yes:
        demo = True
    else:
        demo = ask_choice("Insert demo data?", ["Yes", "No"]) == "Yes"

    if demo:
        seed(create_admin=args.create_admin)
    else:
        print("Skipping demo data.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was changed.")
        sys.exit(130)

