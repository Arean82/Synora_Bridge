"""Database engine selection tests — [Server] environment + enabled flags.

Covers the engine-selection branches in config/settings/base.py (hermetically,
via a fresh interpreter reading a temp config.ini — no live PostgreSQL needed,
since Django only builds the DATABASES dict at import), plus the config-API
PostgreSQL verification gate (`POST /api/v1/config/verify-db/` and the save
fallback in `update_config`).

The suite runs under config.test_settings (backend/pytest.ini), which points
config.ini_config at backend/tests/test_config.ini — so the API tests here
read/write the hermetic fixture, never the developer's real config.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from django.test import Client

from config.ini_config import get_config_dict

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Hermetic engine-selection checks (fresh interpreter + temp config.ini)
# ---------------------------------------------------------------------------

SNIPPET = textwrap.dedent(
    """
    import json
    import os
    import sys
    from pathlib import Path

    import config.ini_config as ic

    ic.DEFAULT_PATH = Path(sys.argv[1])
    ic.load_ini.cache_clear()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings

    print(json.dumps({"engine": settings.DATABASES["default"]["ENGINE"]}))
    """
)

# Production cases need the invariant-satisfying extras.
_PROD = (
    "\ndebug = false\n"
    "[SECURITY]\nsecret_key = x\nencryption_key = y\n"
    "[CELERY]\nalways_eager = false\n"
)

# (name, ini body, expected engine, expected startup error substring or None)
_ENGINE_CASES = [
    # development is strictly SQLite — the enabled flags are ignored.
    (
        "dev_default",
        "[Server]\nenvironment = development\n",
        "django.db.backends.sqlite3",
        None,
    ),
    (
        "dev_ignores_postgres_enabled",
        "[Server]\nenvironment = development\n"
        "[POSTGRES]\nenabled = true\n",
        "django.db.backends.sqlite3",
        None,
    ),
    # production defaults: POSTGRES disabled, SQLITE enabled -> SQLite.
    (
        "prod_missing_flags_defaults_sqlite",
        "[Server]\nenvironment = production" + _PROD,
        "django.db.backends.sqlite3",
        None,
    ),
    (
        "prod_sqlite_explicit",
        "[Server]\nenvironment = production\n"
        "[POSTGRES]\nenabled = false\n[SQLITE]\nenabled = true\n" + _PROD,
        "django.db.backends.sqlite3",
        None,
    ),
    (
        "prod_postgresql",
        "[Server]\nenvironment = production\n"
        "[POSTGRES]\nenabled = true\nhost = localhost\nport = 5432\n"
        "database = bridge_db\nusername = postgres\npassword = \n"
        "[SQLITE]\nenabled = false\n" + _PROD,
        "django.db.backends.postgresql",
        None,
    ),
    (
        "prod_both_enabled_rejected",
        "[Server]\nenvironment = production\n"
        "[POSTGRES]\nenabled = true\n[SQLITE]\nenabled = true\n" + _PROD,
        None,
        "exactly one",
    ),
    (
        "prod_both_disabled_rejected",
        "[Server]\nenvironment = production\n"
        "[POSTGRES]\nenabled = false\n[SQLITE]\nenabled = false\n" + _PROD,
        None,
        "exactly one",
    ),
]


@pytest.mark.parametrize(
    "name,ini_text,expected,error_text",
    _ENGINE_CASES,
    ids=[case[0] for case in _ENGINE_CASES],
)
def test_database_engine_selection(tmp_path, name, ini_text, expected, error_text):
    ini = tmp_path / "config.ini"
    ini.write_text(ini_text, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", SNIPPET, str(ini)],
        cwd=Path(__file__).resolve().parents[1],  # backend/
        capture_output=True,
        text=True,
        timeout=120,
    )
    if error_text:
        assert proc.returncode != 0, f"expected startup failure; got stdout: {proc.stdout}"
        assert error_text in proc.stderr
        return
    assert proc.returncode == 0, f"startup failed; stderr: {proc.stderr}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["engine"] == expected


# ---------------------------------------------------------------------------
# Config API: PostgreSQL verification endpoint + save gate (hermetic fixture)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return Client()


def _unreachable_pg_payload():
    """Full [POSTGRES] section pointing at a closed port (fast refusal)."""
    return {
        "enabled": "true",
        "host": "127.0.0.1",
        "port": "1",
        "database": "bridge_db",
        "username": "postgres",
        "password": "x",
    }


def test_verify_db_failure_reports_error(client):
    r = client.post(
        "/api/v1/config/verify-db/",
        data=json.dumps(_unreachable_pg_payload()),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


def test_put_postgres_enable_without_verified_connection_falls_back_to_sqlite(client):
    """Enabling [POSTGRES] without a working connection must not persist."""
    before = get_config_dict()
    r = client.put(
        "/api/v1/config/",
        data=json.dumps({"sections": {"POSTGRES": _unreachable_pg_payload()}}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["db_fallback"]["requested"] == "postgresql"
    assert body["db_fallback"]["applied"] == "sqlite"
    assert "not verified" in body["db_fallback"]["reason"]
    # Nothing DB-related was persisted.
    after = get_config_dict()
    assert after["POSTGRES"]["enabled"] == before["POSTGRES"]["enabled"] == "false"
    assert after["SQLITE"]["enabled"] == before["SQLITE"]["enabled"] == "true"


def test_put_sqlite_enabled_is_stable(client):
    """SQLite enabled (already the value) — no gate, no db_fallback, and the
    mutual-exclusion normalization keeps POSTGRES disabled."""
    before = get_config_dict()
    sqlite_payload = dict(before["SQLITE"])
    sqlite_payload["enabled"] = "true"
    r = client.put(
        "/api/v1/config/",
        data=json.dumps({"sections": {"SQLITE": sqlite_payload}}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert "db_fallback" not in body
    after = get_config_dict()
    assert after["SQLITE"]["enabled"] == "true"
    assert after["POSTGRES"]["enabled"] == "false"
    assert after == before  # no pollution
