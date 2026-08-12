"""System Configuration API tests — config.ini read/write (Phase 1 restoration)."""
import json

import pytest
from django.test import Client

from config.ini_config import get_config_dict

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def _snapshot():
    """Return a copy of the current config so tests can restore it."""
    return json.loads(json.dumps(get_config_dict()))


def _restore_db_flags(client, snapshot):
    """Restore the POSTGRES/SQLITE enabled flags after a DB-engine test."""
    client.put(
        "/api/v1/config/",
        data=json.dumps({
            "sections": {
                "POSTGRES": {"enabled": snapshot["POSTGRES"]["enabled"]},
                "SQLITE": {"enabled": snapshot["SQLITE"]["enabled"]},
            }
        }),
        content_type="application/json",
    )


def test_disable_sqlite_enables_postgres_when_verified(client, settings, monkeypatch):
    """Disabling SQLite must ENABLE PostgreSQL (exactly-one invariant), after
    the PostgreSQL connection is verified."""
    from apps.core.services import config_service

    monkeypatch.setattr(config_service, "verify_postgres_connection", lambda *a, **k: (True, ""))
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"SQLITE": {"enabled": "false"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json().get("db_fallback") is None
        cfg = get_config_dict()
        assert cfg["SQLITE"]["enabled"] == "false"
        assert cfg["POSTGRES"]["enabled"] == "true"
    finally:
        _restore_db_flags(client, snapshot)


def test_disable_sqlite_unverified_keeps_sqlite(client, settings, monkeypatch):
    """If PostgreSQL cannot be verified, disabling SQLite must not persist —
    SQLite stays enabled and the response carries db_fallback."""
    from apps.core.services import config_service

    monkeypatch.setattr(
        config_service, "verify_postgres_connection", lambda *a, **k: (False, "connection refused")
    )
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"SQLITE": {"enabled": "false"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["db_fallback"] is not None
        assert body["db_fallback"]["applied"] == "sqlite"
        cfg = get_config_dict()
        assert cfg["SQLITE"]["enabled"] == "true"
        assert cfg["POSTGRES"]["enabled"] == "false"
    finally:
        _restore_db_flags(client, snapshot)


def test_disable_postgres_enables_sqlite(client, settings):
    """Disabling PostgreSQL must enable SQLite (no gate needed)."""
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"POSTGRES": {"enabled": "false"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        cfg = get_config_dict()
        assert cfg["POSTGRES"]["enabled"] == "false"
        assert cfg["SQLITE"]["enabled"] == "true"
    finally:
        _restore_db_flags(client, snapshot)


def test_enable_postgres_verified_disables_sqlite(client, settings, monkeypatch):
    """Enabling PostgreSQL directly (verified) must disable SQLite."""
    from apps.core.services import config_service

    monkeypatch.setattr(config_service, "verify_postgres_connection", lambda *a, **k: (True, ""))
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"POSTGRES": {"enabled": "true"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        cfg = get_config_dict()
        assert cfg["POSTGRES"]["enabled"] == "true"
        assert cfg["SQLITE"]["enabled"] == "false"
    finally:
        _restore_db_flags(client, snapshot)


def test_get_full_config(client, settings):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    r = client.get("/api/v1/config/")
    assert r.status_code == 200
    sections = r.json()["sections"]

    real = get_config_dict()
    # Every real section + key is present, typed, and value matches disk.
    for sec, keys in real.items():
        assert sec in sections
        for key, val in keys.items():
            entry = sections[sec][key]
            assert entry["value"] == str(val)
            assert entry["type"] in ("str", "int", "bool")
    # No extra sections invented.
    assert len(sections) == len(real)


def test_put_updates_value_and_roundtrips(client, settings):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"UI": {"layout": "topbar"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json()["updated"] == ["UI.layout"]
        assert r.json()["restart_required"] is False
        assert get_config_dict()["UI"]["layout"] == "topbar"
    finally:
        client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"UI": {"layout": snapshot["UI"]["layout"]}}}),
            content_type="application/json",
        )


def test_put_core_key_requires_restart(client, settings):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"Server": {"debug": "false"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert "Server.debug" in body["updated"]
        assert body["restart_required"] is True
        assert "Server.debug" in body["restart_keys"]
    finally:
        client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"Server": {"debug": snapshot["Server"]["debug"]}}}),
            content_type="application/json",
        )


def test_put_unknown_section_rejected(client, settings):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    r = client.put(
        "/api/v1/config/",
        data=json.dumps({"sections": {"NOPE": {"a": "b"}}}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "NOPE" in r.json()["error"]


def test_put_unknown_key_rejected(client, settings):
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    r = client.put(
        "/api/v1/config/",
        data=json.dumps({"sections": {"Server": {"bogus": "x"}}}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "Server.bogus" in r.json()["error"]


def test_config_parses_percent_values(client, settings, tmp_path):
    """Regression: passwords/URLs containing % must parse without
    InterpolationSyntaxError (configparser default interpolation would fail)."""
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

    cfg = tmp_path / "config.ini"
    cfg.write_text(
        "[EMAIL]\n"
        "smtp_password = p@ss%w0rd!%20\n"
        "mode = smtp\n"
        "[Server]\n"
        "timezone = Asia/Kolkata\n",
        encoding="utf-8",
    )
    from config.ini_config import get_config_dict

    data = get_config_dict(cfg)
    assert data["EMAIL"]["smtp_password"] == "p@ss%w0rd!%20"
