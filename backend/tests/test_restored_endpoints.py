"""Phase 2 restored endpoints — validate, test_mapping, per-connection docs/playground."""
import json

import pytest
from django.test import Client

from apps.connections.models import Connection

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


VALID_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Demo Spec", "version": "1.0"},
    "paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
}


def test_validate_paste_success(client):
    r = client.post(
        "/api/v1/connections/validate/",
        data=json.dumps({"source_type": "paste", "content": json.dumps(VALID_SPEC)}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["operation_count"] == 1
    assert body["spec_version"] == "OpenAPI 3.0.3"


def test_validate_yaml_spec(client):
    yaml_spec = (
        "openapi: 3.0.3\n"
        "info:\n  title: YAML Spec\n  version: '1'\n"
        "paths:\n  /y:\n    get:\n      responses:\n        '200':\n          description: ok\n"
    )
    r = client.post(
        "/api/v1/connections/validate/",
        data=json.dumps({"source_type": "paste", "content": yaml_spec}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_validate_bad_paste_rejected(client):
    r = client.post(
        "/api/v1/connections/validate/",
        data=json.dumps({"source_type": "paste", "content": "not a spec"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_validate_ssrf_blocks_localhost(client):
    r = client.post(
        "/api/v1/connections/validate/",
        data=json.dumps({"source_type": "url", "url": "http://127.0.0.1:8874/spec.json"}),
        content_type="application/json",
    )
    assert r.json()["success"] is False
    assert "SSRF" in r.json()["error"]


def test_post_views_are_csrf_exempt(client):
    """Regression: plain-Django API POST views must not be CSRF-blocked for
    real (non-browser) clients. The Django test client never enforces CSRF,
    so this must be asserted via Client(enforce_csrf_checks=True)."""
    client = Client(enforce_csrf_checks=True)
    r = client.post(
        "/api/v1/test_mapping/",
        data=json.dumps({"mapping": [{"source": "a", "target": "b"}]}),
        content_type="application/json",
    )
    assert r.status_code == 200, f"test_mapping blocked by CSRF: {r.status_code}"
    assert r.json()["sample_payload"] == {"b": "<Sample a>"}


def test_test_mapping_nested_payload(client):
    r = client.post(
        "/api/v1/test_mapping/",
        data=json.dumps({
            "mapping": [
                {"source": "source_0.name", "target": "company.name"},
                {"source": "source_0.lat", "target": "gps[0].latitude"},
            ],
        }),
        content_type="application/json",
    )
    assert r.status_code == 200
    payload = r.json()["sample_payload"]
    assert payload["company"]["name"] == "<Sample source_0.name>"
    assert payload["gps"][0]["latitude"] == "<Sample source_0.lat>"


def test_connection_docs_page(client):
    conn = Connection.objects.create(
        name="Docs Test",
        is_local_file=True,
        json_content=json.dumps({
            "openapi": "3.0.3",
            "info": {"title": "Conn Spec", "version": "1"},
            "paths": {"/a": {"get": {"responses": {"200": {"description": "ok"}}}}},
        }),
        connection_type="rest",
    )
    r = client.get(f"/api/v1/docs/{conn.pk}/")
    assert r.status_code == 200
    assert "swagger-ui" in r.content.decode()
    assert "Conn Spec" in r.content.decode()


def test_connection_graphql_test_page(client):
    rest = Connection.objects.create(
        name="Rest",
        is_local_file=True,
        json_content="{}",
        connection_type="rest",
    )
    assert client.get(f"/api/v1/graphql/test/{rest.pk}/").status_code == 400

    gql = Connection.objects.create(
        name="Gql",
        is_local_file=True,
        json_content="{}",
        connection_type="graphql",
        url="http://127.0.0.1:8874/graphql",
    )
    r = client.get(f"/api/v1/graphql/test/{gql.pk}/")
    assert r.status_code == 200
    assert "GraphiQL" in r.content.decode()


def test_graphql_dest_specific_and_redirect(client, mock_source_url):
    """Bare slug redirects to first dest; dest-specific executes its mapping."""
    from apps.configs.models import Template

    tpl = Template.objects.create(
        name="GQL Dest Test",
        execution_mode="pull_graphql",
        sources=[{"name": "m", "url": mock_source_url, "source_type": "rest", "method": "GET"}],
        destinations=[
            {"name": "Client Alpha", "method": "GET", "field_mapping": [{"source": "source_0.name", "target": "data[0].name"}]},
            {"name": "Client Beta", "method": "GET", "field_mapping": [{"source": "source_0.gps_lat", "target": "lat"}]},
        ],
    )
    try:
        r = client.get(f"/api/v1/bridge/graphql/{tpl.slug}/")
        assert r.status_code == 302
        assert "client_alpha" in r.headers["Location"]

        r = client.get(f"/api/v1/bridge/graphql/{tpl.slug}/client_alpha/")
        assert r.status_code == 200
        assert "GraphiQL" in r.content.decode()

        r = client.post(
            f"/api/v1/bridge/graphql/{tpl.slug}/client_alpha/",
            data=json.dumps({"query": "{ data { data { name } } }"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json()["data"]["data"]["data"][0]["name"] == "Acme"

        # Second destination has a different mapping (lat target).
        r = client.post(
            f"/api/v1/bridge/graphql/{tpl.slug}/client_beta/",
            data=json.dumps({"query": "{ data { lat } }"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.json()["data"]["data"]["lat"] == "10.5"
    finally:
        tpl.delete()


def test_graphql_auth_parity(client, mock_source_url):
    """Regression (original parity): GraphQL playground is public; data
    execution requires the per-template bearer token."""
    from apps.configs.models import Template

    tpl = Template.objects.create(
        name="GQL Auth Parity",
        execution_mode="pull_graphql",
        sources=[{"name": "m", "url": mock_source_url, "source_type": "rest", "method": "GET"}],
        destinations=[{"name": "c1", "method": "GET", "field_mapping": [{"source": "source_0.name", "target": "data[0].name"}]}],
        client_credentials={"token": "parity-token"},
    )
    try:
        # Playground GET is public — no auth needed.
        r = client.get(f"/api/v1/bridge/graphql/{tpl.slug}/c1/")
        assert r.status_code == 200
        assert "GraphiQL" in r.content.decode()

        # Execution POST without token → 401.
        r = client.post(
            f"/api/v1/bridge/graphql/{tpl.slug}/c1/",
            data=json.dumps({"query": "{ data { data { name } } }"}),
            content_type="application/json",
        )
        assert r.status_code == 401

        # With the token → 200 + real data.
        r = client.post(
            f"/api/v1/bridge/graphql/{tpl.slug}/c1/",
            data=json.dumps({"query": "{ data { data { name } } }"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer parity-token",
        )
        assert r.status_code == 200
        assert r.json()["data"]["data"]["data"][0]["name"] == "Acme"
    finally:
        tpl.delete()


def test_doc_content_endpoint(client, settings):
    """Docs viewer (original docs modal parity): README + docs/*.md, traversal-safe."""
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    r = client.get("/api/v1/docs/markdown/README.md/")
    assert r.status_code == 200
    assert "content" in r.json()
    assert "#" in r.json()["content"]  # markdown present

    r = client.get("/api/v1/docs/markdown/ARCHITECTURE.md/")
    assert r.status_code == 200

    # Traversal attempts rejected.
    for evil in ["..%2F..%2Fconfig.ini", "..\\..\\config.ini", "noext.txt"]:
        r = client.get(f"/api/v1/docs/markdown/{evil}/")
        assert r.status_code in (400, 404)


def test_doc_content_sanitized_html(client, settings):
    """Docs are rendered server-side and XSS-stripped with bleach (reference-
    repo pattern): tables/fenced code render, script tags + event handlers
    are removed."""
    import bleach
    import markdown

    raw = (
        "# Header\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "```python\nprint('hi')\n```\n\n<script>alert(1)</script>\n\n"
        "<img src=x onerror=alert(2)>\n"
    )
    html = markdown.markdown(raw, extensions=["extra", "tables", "fenced_code", "codehilite", "sane_lists", "toc"])
    safe = bleach.clean(
        html,
        tags=[
            "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
            "strong", "em", "del", "code", "pre", "blockquote",
            "ul", "ol", "li", "dl", "dt", "dd",
            "table", "thead", "tbody", "tr", "th", "td",
            "a", "img", "span", "div",
        ],
        attributes={
            "a": ["href", "title", "target", "rel"],
            "img": ["src", "alt", "title"],
            "code": ["class"],
            "th": ["align"], "td": ["align"],
            "span": ["class"],
        },
        protocols=["http", "https", "mailto"],
    )
    assert "<h1>" in safe and "Header" in safe
    assert "<table>" in safe and "<td>1</td>" in safe
    assert "<pre>" in safe and "print" in safe
    # Executable script tag and event-handler attribute must be removed.
    assert "<script" not in safe
    assert "onerror" not in safe


def test_email_templates_crud_and_traversal(client, settings, tmp_path):
    """Email template list/read/write + path-traversal hardening."""
    from apps.core.services import email_templates

    # Point the service at a temp dir so tests never touch the real templates.
    tmp = tmp_path / "email"
    tmp.mkdir()
    (tmp / "failure_alert.html").write_text("<html>ORIGINAL</html>", encoding="utf-8")
    email_templates.EMAIL_TEMPLATE_DIR = tmp

    r = client.get("/api/v1/email-templates/")
    assert r.status_code == 200
    assert "failure_alert.html" in r.json()["templates"]

    r = client.get("/api/v1/email-templates/failure_alert.html/")
    assert r.status_code == 200
    assert "ORIGINAL" in r.json()["content"]

    r = client.put(
        "/api/v1/email-templates/failure_alert.html/",
        data=json.dumps({"content": "<html>UPDATED</html>"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["saved"] is True
    assert (tmp / "failure_alert.html").read_text(encoding="utf-8") == "<html>UPDATED</html>"

    # Traversal attempts must be rejected (the original only checked .html).
    for evil in ["../config.ini", "..%2Fconfig.ini", "noext"]:
        r = client.get(f"/api/v1/email-templates/{evil}/")
        assert r.status_code in (400, 404)
