"""DRF API smoke tests (Phase 2 verification, converted to pytest)."""
import json

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def test_health_endpoints(client):
    assert client.get("/api/v1/health/live/").status_code == 200
    assert client.get("/api/v1/health/ready/").status_code == 200
    assert client.get("/api/v1/metrics/").status_code == 200


def test_template_crud(client):
    payload = {
        "name": "API Test Template",
        "execution_mode": "push",
        "pull_method": "GET",
        "sources": [{"name": "s", "url": "https://api.example.com/v1", "source_type": "rest", "selectedApi": "/v1"}],
        "destinations": [{"name": "d", "url": "https://dest.example.com", "method": "POST", "field_mapping": []}],
        "client_credentials": {"token": "secret"},
    }
    r = client.post("/api/v1/templates/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 201
    tpl = r.json()
    assert tpl["slug"] == "api_test_template"
    # Encrypted payload is returned decrypted as real JSON.
    assert tpl["client_credentials"] == {"token": "secret"}

    assert client.get("/api/v1/templates/").status_code == 200
    assert client.get(f"/api/v1/templates/{tpl['id']}/").status_code == 200


def test_template_validation_requires_sources(client):
    r = client.post(
        "/api/v1/templates/",
        data=json.dumps({"name": "No Sources", "sources": []}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_job_toggle_and_beat_sync(client):
    from django_celery_beat.models import PeriodicTask

    from apps.configs.models import Template
    from apps.jobs.models import Job

    tpl = Template.objects.create(name="Job Test", sources=[{"url": "https://x.example", "source_type": "rest", "selectedApi": "/"}])
    job = Job.objects.create(template=tpl, schedule_interval=60, is_active=True)
    assert PeriodicTask.objects.filter(name=f"bridge-job-{job.pk}").exists()

    r = client.post(f"/api/v1/jobs/{job.pk}/toggle/")
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert not PeriodicTask.objects.filter(name=f"bridge-job-{job.pk}").exists()


def test_connection_crud_local_file(client):
    spec = {"openapi": "3.0.3", "info": {"title": "Demo", "version": "1"}, "paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}}}
    payload = {
        "name": "Local Conn",
        "is_local_file": True,
        "json_content": json.dumps(spec),
        "connection_type": "rest",
        "auth_type": "none",
    }
    r = client.post("/api/v1/connections/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 201


def test_settings_and_audit(client):
    r = client.post("/api/v1/settings/", data=json.dumps({"key": "ui.test", "value": {"a": 1}}), content_type="application/json")
    assert r.status_code == 201
    assert client.get("/api/v1/settings/?key=ui.test").status_code == 200
    assert client.get("/api/v1/audit-logs/").status_code == 200


def test_schema_endpoint(client):
    r = client.get("/schema/?format=json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "Synora Bridge API"


def test_template_timezone_roundtrip(client, settings):
    """Per-template IANA timezone: explicit set, default, and invalid rejected."""
    from apps.configs.models import Template

    # Explicit zone is stored and returned.
    r = client.post(
        "/api/v1/templates/",
        data=json.dumps({
            "name": "TZ Test",
            "timezone": "Europe/Berlin",
            "sources": [{"name": "s", "url": "https://x.example", "source_type": "rest", "selectedApi": "/"}],
        }),
        content_type="application/json",
    )
    assert r.status_code == 201
    assert r.json()["timezone"] == "Europe/Berlin"

    # Omitted zone falls back to the global [Server] timezone, not None.
    r = client.post(
        "/api/v1/templates/",
        data=json.dumps({
            "name": "TZ Default",
            "sources": [{"name": "s", "url": "https://x.example", "source_type": "rest", "selectedApi": "/"}],
        }),
        content_type="application/json",
    )
    assert r.status_code == 201
    assert r.json()["timezone"] == settings.TIME_ZONE

    # Invalid zone is rejected with a validation error.
    r = client.post(
        "/api/v1/templates/",
        data=json.dumps({
            "name": "TZ Bad",
            "timezone": "Not/AZone",
            "sources": [{"name": "s", "url": "https://x.example", "source_type": "rest", "selectedApi": "/"}],
        }),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "timezone" in r.json()["details"]

    Template.objects.filter(name__startswith="TZ ").delete()
