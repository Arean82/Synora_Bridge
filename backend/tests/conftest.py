"""Shared pytest fixtures for the Synora Bridge test suite."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from django.conf import settings


class MockApiHandler(BaseHTTPRequestHandler):
    """A tiny mock HTTP source server for engine/pull tests."""

    payload = json.dumps({"name": "Acme", "gps_lat": "10.5", "id": "42"}).encode()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format, *args):  # noqa: A002 - silence request logging
        pass


@pytest.fixture(scope="session")
def mock_source_server():
    """Start a mock HTTP server on 127.0.0.1:8877 for the session."""
    server = HTTPServer(("127.0.0.1", 8877), MockApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()  # release the listening socket (avoids resource warnings)
    thread.join(timeout=5)


@pytest.fixture
def mock_source_url(mock_source_server):
    return "http://127.0.0.1:8877/source"


@pytest.fixture
def push_template(mock_source_url):
    """A ready-to-run push template pointing at the mock source."""
    from apps.configs.models import Template

    tpl = Template.objects.create(
        name=f"Push Test {uuid4().hex[:6]}",
        execution_mode="push",
        sources=[{
            "name": "mock",
            "url": mock_source_url,
            "source_type": "rest",
            "selectedApi": "/source",
            "method": "GET",
            "auth_token": None,
        }],
        destinations=[{
            "name": "dest1",
            "url": mock_source_url,  # mock accepts GET only; engine skips on failure
            "method": "POST",
            "auth_type": "none",
            "credentials": {},
            "field_mapping": [
                {"source": "source_0.name", "target": "company.name"},
                {"source": "source_0.gps_lat", "target": "gps[0].latitude"},
            ],
        }],
        client_credentials={"token": "x"},
    )
    yield tpl
    tpl.delete()


def uuid4():
    import uuid

    return uuid.uuid4()


@pytest.fixture(autouse=True)
def _test_allow_hosts(settings):
    """Allow the testserver host used by Django's test client.

    Django's test environment forces DEBUG=False, so also provide a valid
    ENCRYPTION_KEY (the production key-requirement path) for encryption tests.
    """
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
    if not getattr(settings, "ENCRYPTION_KEY", ""):
        settings.ENCRYPTION_KEY = "mGnSdgOaOVuEpilDk1tA16RNskujSSep6qWmgiT1dwI="  # 32-byte AES-256 test key
    yield


@pytest.fixture(autouse=True)
def _hermetic_cache(settings):
    """Keep the test suite hermetic: no live Redis required.

    The app uses a Redis cache (pull cache + rate limiting) and a Redis
    channel layer in production; tests override both with in-memory backends
    so the suite runs anywhere without Redis/Memurai.
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    yield
