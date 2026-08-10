"""
Synora Bridge — demo seed script (standalone).

Port of the original `scripts/seed_final.py` (Flask) to the Django stack,
kept OUT of the application on purpose: it is a demo/data tool, not needed in
production.

DB-agnostic: uses only the Django ORM, so it works identically on the
development SQLite database and production PostgreSQL (per backend/config.ini).

Demo-ready guarantees:
- Template source URLs come from a curated list of KEYLESS public APIs; every
  URL is probed live at seed time and only used if it returns HTTP 200 with a
  JSON body. Pull endpoints therefore return REAL, LIVE data in the demo
  (JSONPlaceholder, REST Countries, PokeAPI, SpaceX, Open-Meteo, ...).
- Field mappings are derived from those real response field names (including
  list-aware nested targets such as data[0].<field>).
- Connection records are seeded from real public OpenAPI/Swagger specs
  (Connections page, Swagger UI and mock server use them).
- Seeds JobLog history (dashboard runs), AppSettings (UI theme/layout) and an
  optional demo admin user.

Usage (from anywhere — resolves the backend relative to this file):

    python scripts/seed_demo.py
    python scripts/seed_demo.py --create-admin   # also create admin/admin123

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
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

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

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (SynoraBridge Demo)"}

# ---------------------------------------------------------------------------
# Keyless public APIs — guaranteed real data for a live demo.
# Each entry is (name, url, sample_field_names). At seed time every URL is
# probed; only sources returning HTTP 200 with a JSON body are used, so the
# demo always shows real, live data (no keys required).
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
    ("Petstore API", "https://petstore.swagger.io/v2/swagger.json"),
    ("Weather.gov API", "https://api.weather.gov/openapi.json"),
    ("REST Countries", "https://restcountries.com/v3.1/openapi.json"),
    ("JSONPlaceholder", "https://jsonplaceholder.typicode.com/openapi.json"),
    ("GitHub API", "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"),
]


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
                is_active=True,
                connection_type="rest",
                auth_type="none",
                schema_source="introspection",
                spec_auth_type="none",
            )
        created += 1
        print(f"  + Connection: {conn.name}")
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

    # --- 6 single-destination push templates (real fetch → httpbin) ---
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

    # --- 6 REST pull templates (single real source → mapped endpoint) ---
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

    # --- 4 REST pull templates (multi-source aggregation → one endpoint) ---
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


def seed(create_admin=False):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Synora Bridge demo database.")
    parser.add_argument("--create-admin", action="store_true", help="Create demo admin user (admin/admin123).")
    args = parser.parse_args()
    seed(create_admin=args.create_admin)
