"""Live (no-restart) settings + validated auto-restart scheduling tests.

Auto-restart never fires in the suite: `AUTO_RESTART_ON_SAVE = False` in
config/test_settings.py, and the restart tests additionally stub the
pre-flight check + scheduler so nothing is ever re-exec'd.
"""
import json

import pytest
from django.test import Client

import config.ini_config as ic
from config import live_settings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_live_cache():
    live_settings.clear_cache()
    yield
    live_settings.clear_cache()


def _snapshot():
    return json.loads(json.dumps(ic.get_config_dict()))


def _restore(cfg):
    for section, keys in cfg.items():
        for key, value in keys.items():
            ic.set_ini_value(ic.DEFAULT_PATH, section, key, value)
    live_settings.clear_cache()


# ---------------------------------------------------------------------------
# Live settings read + apply without restart
# ---------------------------------------------------------------------------
def test_live_reads_fixture_values():
    assert live_settings.live.EMAIL_MODE == "none"
    assert live_settings.live.RATE_LIMIT_ENABLED is True
    assert live_settings.live.PULL_CACHE_ENABLED is True
    assert live_settings.live.RETRY_QUEUE_RETENTION_MINUTES == 60
    assert "http://localhost:3000" in live_settings.live.CORS_ALLOWED_ORIGINS


def test_live_value_updates_after_save():
    snapshot = _snapshot()
    try:
        ic.set_ini_value(ic.DEFAULT_PATH, "EMAIL", "mode", "smtp")
        live_settings.clear_cache()
        assert live_settings.live.EMAIL_MODE == "smtp"
    finally:
        _restore(snapshot)


def test_live_cors_list_updates_after_save():
    snapshot = _snapshot()
    try:
        ic.set_ini_value(ic.DEFAULT_PATH, "CORS", "allowed_origins", "http://app.example,http://api.example")
        live_settings.clear_cache()
        origins = list(live_settings.live.CORS_ALLOWED_ORIGINS)
        assert origins == ["http://app.example", "http://api.example"]
        assert "http://localhost:3000" not in origins
    finally:
        _restore(snapshot)


# ---------------------------------------------------------------------------
# Validated auto-restart on core saves
# ---------------------------------------------------------------------------
def test_core_save_schedules_restart(client, monkeypatch):
    """Saving a restart-required key (valid config) schedules the in-place
    restart and reports it in the response."""
    import apps.core.views_config as views_config

    monkeypatch.setattr(views_config, "_auto_restart_enabled", lambda: True)
    monkeypatch.setattr(views_config, "_config_boots", lambda *a, **k: (True, ""))
    scheduled = []
    monkeypatch.setattr(
        views_config, "_schedule_restart", lambda host, port, delay=0.75: scheduled.append((host, port))
    )

    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"Server": {"allowed_hosts": "127.0.0.1,localhost,newhost"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["restart_scheduled"] is True
        assert "Server.allowed_hosts" in body["restart_keys"]
        # Fixture [Server] host/port drive the daphne rebind args.
        assert scheduled == [("127.0.0.1", "8000")]
    finally:
        _restore(snapshot)


def test_core_save_blocked_when_config_would_not_boot(client, monkeypatch):
    """A config that fails the pre-flight check must NOT schedule a restart —
    the response carries restart_blocked and the server stays up."""
    import apps.core.views_config as views_config

    monkeypatch.setattr(views_config, "_auto_restart_enabled", lambda: True)
    monkeypatch.setattr(views_config, "_config_boots", lambda *a, **k: (False, "production invariants broken"))
    scheduled = []
    monkeypatch.setattr(
        views_config, "_schedule_restart", lambda host, port, delay=0.75: scheduled.append((host, port))
    )

    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"Server": {"allowed_hosts": "127.0.0.1,localhost,newhost"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert "restart_scheduled" not in body
        assert body["restart_blocked"]["error"] == "production invariants broken"
        assert scheduled == []
    finally:
        _restore(snapshot)


def test_live_key_save_does_not_restart(client):
    """Saving a live-applicable key never schedules a restart."""
    import apps.core.views_config as views_config

    snapshot = _snapshot()
    try:
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"CORS": {"allowed_origins": "http://x.example"}}}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["restart_keys"] == []
        assert "restart_scheduled" not in body
        assert "restart_blocked" not in body
    finally:
        _restore(snapshot)


def test_auto_restart_disabled_in_suite(client):
    """AUTO_RESTART_ON_SAVE=False in tests: a core-key save never schedules."""
    import apps.core.views_config as views_config

    scheduled = []
    monkeypatch_schedule = None
    # _auto_restart_enabled() already reads the test setting (False) — assert
    # no scheduling happens through the default path.
    monkeypatch_schedule = __import__("pytest").MonkeyPatch()
    monkeypatch_schedule.setattr(
        views_config, "_schedule_restart", lambda host, port, delay=0.75: scheduled.append((host, port))
    )
    try:
        snapshot = _snapshot()
        r = client.put(
            "/api/v1/config/",
            data=json.dumps({"sections": {"Server": {"allowed_hosts": "127.0.0.1,localhost,newhost"}}}),
            content_type="application/json",
        )
        body = r.json()
        assert body["restart_required"] is True
        assert "restart_scheduled" not in body
        assert scheduled == []
        _restore(snapshot)
    finally:
        monkeypatch_schedule.undo()
