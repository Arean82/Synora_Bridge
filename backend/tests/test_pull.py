"""Pull mode tests — REST endpoints, specs, auth, rate limit, GraphQL, mock."""
import json

import pytest
from django.test import Client

from apps.configs.models import Template

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def pull_template(mock_source_url):
    tpl = Template.objects.create(
        name="Pull Test Template",
        execution_mode="pull_rest",
        sources=[{"name": "mock", "url": mock_source_url, "source_type": "rest", "selectedApi": "/source", "method": "GET"}],
        destinations=[{
            "name": "client1",
            "method": "GET",
            "field_mapping": [
                {"source": "source_0.name", "target": "company.name"},
                {"source": "source_0.gps_lat", "target": "gps[0].latitude"},
            ],
        }],
        client_credentials={"token": "demo-token"},
    )
    yield tpl
    tpl.delete()


def test_pull_rest_endpoint(client, pull_template):
    r = client.get(f"/api/v1/bridge/pull/{pull_template.slug}/client1/", HTTP_AUTHORIZATION="Bearer demo-token")
    assert r.status_code == 200
    data = r.json()
    assert data["company"]["name"] == "Acme"
    assert data["gps"][0]["latitude"] == "10.5"


def test_pull_rest_requires_auth(client, pull_template):
    r = client.get(f"/api/v1/bridge/pull/{pull_template.slug}/client1/")
    assert r.status_code == 401
    r = client.get(f"/api/v1/bridge/pull/{pull_template.slug}/client1/", HTTP_AUTHORIZATION="Bearer wrong")
    assert r.status_code == 401


def test_pull_rest_404_unknown_template(client):
    r = client.get("/api/v1/bridge/pull/does_not_exist/client1/")
    assert r.status_code in (404, 401)  # 404 from APIError handler


@pytest.mark.parametrize("version,label", [
    ("3.2.0", "openapi"),
    ("3.1.0", "openapi"),
    ("3.0.3", "openapi"),
    ("2.0", "swagger"),
])
def test_spec_versions(client, pull_template, version, label):
    r = client.get(f"/api/v1/bridge/pull/{pull_template.slug}/spec?version={version}")
    assert r.status_code == 200
    assert label in r.content.decode()


def test_swagger_ui_docs(client, pull_template):
    r = client.get(f"/api/v1/bridge/pull/{pull_template.slug}/docs")
    assert r.status_code == 200
    assert "swagger-ui" in r.content.decode()


def test_rate_limit_429(client, mock_source_url):
    from django.core.cache import cache

    cache.clear()
    # Rate limiting is config-driven (config/live_settings.py): write a small
    # rate to the test fixture and restore it afterwards.
    import config.ini_config as ic
    from config import live_settings

    original_rate = ic.get_config_dict().get("RateLimit", {}).get("rate", "60")
    try:
        ic.set_ini_value(ic.DEFAULT_PATH, "RateLimit", "rate", "3")
        live_settings.clear_cache()

        tpl = Template.objects.create(
            name="Rate Test",
            execution_mode="pull_rest",
            sources=[{"name": "m", "url": mock_source_url, "source_type": "rest"}],
            destinations=[{"name": "c1", "method": "GET", "field_mapping": []}],
        )
        try:
            statuses = [client.get(f"/api/v1/bridge/pull/{tpl.slug}/c1/").status_code for _ in range(6)]
            assert statuses.count(429) >= 1
            assert statuses[:3] == [200, 200, 200]
        finally:
            tpl.delete()
            cache.clear()
    finally:
        ic.set_ini_value(ic.DEFAULT_PATH, "RateLimit", "rate", original_rate)
        live_settings.clear_cache()


def test_graphql_dynamic_schema(client, mock_source_url):
    gql = Template.objects.create(
        name="GQL Pull Test",
        execution_mode="pull_graphql",
        sources=[{"name": "mock", "url": mock_source_url, "source_type": "rest", "selectedApi": "/source", "method": "GET"}],
        destinations=[{
            "name": "c1",
            "method": "GET",
            "field_mapping": [
                {"source": "source_0.name", "target": "company.name"},
                {"source": "source_0.gps_lat", "target": "gps[0].latitude"},
            ],
        }],
    )
    try:
        # Bare slug redirects to the first destination (original parity).
        r = client.get(f"/api/v1/bridge/graphql/{gql.slug}/")
        assert r.status_code == 302
        assert "c1" in r.headers["Location"]

        # Dest-specific GET renders the GraphiQL playground.
        r = client.get(f"/api/v1/bridge/graphql/{gql.slug}/c1/")
        assert r.status_code == 200
        assert "GraphiQL" in r.content.decode()

        r = client.post(
            f"/api/v1/bridge/graphql/{gql.slug}/c1/",
            data=json.dumps({"query": "{ data { company { name } gps { latitude } } }"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["data"]["company"]["name"] == "Acme"
    finally:
        gql.delete()


def test_mock_server(client):
    from apps.connections.models import Connection

    conn = Connection.objects.create(
        name="Mock Conn",
        is_local_file=True,
        json_content=json.dumps({
            "openapi": "3.0.3",
            "info": {"title": "Demo", "version": "1"},
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {"application/json": {"example": {"id": 1, "name": "Alice"}}},
                            }
                        }
                    }
                }
            },
        }),
    )
    try:
        r = client.get(f"/api/v1/mock/{conn.pk}/users/42")
        assert r.status_code == 200
        assert r.json()["name"] == "Alice"

        r = client.get(f"/api/v1/mock/{conn.pk}/unknown")
        assert r.status_code == 404
    finally:
        conn.delete()
