"""
Pull mode views — auto-generated REST + GraphQL endpoints and the mock server.

Ports the original pull controllers (pull_rest, pull_graphql, mock_server) onto
DRF/plain Django views with the approved scale items:
- per-template bearer auth (#9): client_credentials.token must match
  the Authorization: Bearer header when configured
- rate limiting (#5): django-ratelimit, Redis-backed, config.ini [RateLimit]
- short-TTL response cache (#2): Redis, config.ini [Cache]
- async upstream fetch (#3): httpx/asyncio
"""
import json
import logging
import functools

import redis.exceptions
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.configs.models import Template
from config.live_settings import live
from apps.core.errors import api_error_response
from apps.core.exceptions import APIError
from apps.pull.services.async_fetch import fetch_all_sources_async
from apps.pull.services.openapi_spec import (
    generate_pull_endpoint_spec,
    get_swagger_ui_html,
)
from apps.pull.services.strawberry_dynamic import execute_graphql

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_template_by_slug(slug):
    """O(1) indexed lookup (scale item #1)."""
    return Template.objects.filter(slug=slug).first()


def _check_client_auth(template, request):
    """Per-template bearer auth (#9): if the template has a client token,
    the request must present it. Returns error response or None."""
    creds = template.client_credentials or {}
    token = creds.get("token")
    if not token:
        return None
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {token}"
    if auth_header != expected:
        return JsonResponse(
            {"status": "error", "message": "Unauthorized", "code": 401}, status=401
        )
    return None


def _pull_cache_key(slug, dest):
    return f"pull:{slug}:{dest}"


def _get_cached(slug, dest):
    if not live.PULL_CACHE_ENABLED:
        return None
    from django.core.cache import cache

    try:
        return cache.get(_pull_cache_key(slug, dest))
    except Exception:
        # Fail-open: a Redis outage must not break pull endpoints.
        logger.warning("Pull cache read failed (Redis down?) — serving fresh.", exc_info=True)
        return None


def _set_cached(slug, dest, value) -> None:
    if not live.PULL_CACHE_ENABLED:
        return
    from django.core.cache import cache

    try:
        cache.set(_pull_cache_key(slug, dest), value, timeout=live.PULL_CACHE_TTL_SECONDS)  # type: ignore[arg-type]
    except Exception:
        # Fail-open: cache write failure is non-fatal.
        logger.warning("Pull cache write failed (Redis down?) — skipping cache.", exc_info=True)


def _execute_pull(template, dest_slug=None):
    """Fetch sources (async) and build the transformed payload for a dest."""
    from apps.core.services.data_transform import build_nested_payload

    aggregated = fetch_all_sources_async(template.sources or [])
    destinations = template.destinations or []
    if dest_slug:
        dest = next((d for d in destinations if _dest_slug(d.get("name")) == dest_slug), None)
    else:
        dest = destinations[0] if destinations else None

    if not dest:
        return aggregated

    mapping = dest.get("field_mapping", [])
    if mapping:
        return build_nested_payload(mapping, aggregated)
    return aggregated


def _dest_slug(name):
    slug = (name or "default").lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in slug if c.isalnum() or c == "_")


def _rate_limit_config(group=None, request=None):
    """Return (rate, period) from config.ini [RateLimit] for django-ratelimit.

    Read live so a [RateLimit] change applies without a restart.
    """
    return f"{live.RATE_LIMIT_RATE}/{live.RATE_LIMIT_PERIOD}"


def safe_ratelimit(*args, **kwargs):
    """Rate-limit a view but FAIL OPEN when the cache (Redis) is unavailable.

    django-ratelimit raises ConnectionError when its backing cache is down;
    that must never take pull endpoints down with it. On cache errors the
    view runs un-limited (degraded, not broken).
    """
    def _decorator(view_func):
        wrapped = ratelimit(*args, **kwargs)(view_func)

        @functools.wraps(view_func)
        def _handler(request, *view_args, **view_kwargs):
            try:
                return wrapped(request, *view_args, **view_kwargs)
            except (redis.exceptions.RedisError, ConnectionError):
                logger.warning("Rate-limit cache unavailable — serving un-limited.", exc_info=True)
                return view_func(request, *view_args, **view_kwargs)

        return _handler

    return _decorator


def _maybe_rate_limited(request):
    """If rate limiting is enabled and the request was limited, return a 429."""
    if live.RATE_LIMIT_ENABLED and getattr(request, "limited", False):
        return JsonResponse(
            {"status": "error", "message": "Rate limit exceeded. Try again later.", "code": 429},
            status=429,
        )
    return None


# ---------------------------------------------------------------------------
# REST pull
# ---------------------------------------------------------------------------
@csrf_exempt
@safe_ratelimit(key="ip", rate=_rate_limit_config, block=False)
@require_http_methods(["GET", "POST", "PUT", "PATCH", "DELETE"])
@api_error_response
def pull_rest_endpoint(request, slug, dest_slug):
    """Serve the auto-generated pull REST endpoint for a template."""
    limited = _maybe_rate_limited(request)
    if limited:
        return limited

    template = _get_template_by_slug(slug)
    if not template:
        raise APIError("Template not found.", 404)

    auth_error = _check_client_auth(template, request)
    if auth_error:
        return auth_error

    if request.method == "GET":
        cached = _get_cached(slug, dest_slug)
        if cached is not None:
            return JsonResponse(cached)
        payload = _execute_pull(template, dest_slug)
        _set_cached(slug, dest_slug, payload)
        return JsonResponse(payload)

    # Non-GET methods force a fresh fetch (bypass cache).
    payload = _execute_pull(template, dest_slug)
    return JsonResponse(payload)


@require_GET
@api_error_response
def pull_rest_spec(request, slug):
    """Serve the generated OpenAPI spec (2.0 / 3.0.3 / 3.1.0 / 3.2.0)."""
    template = _get_template_by_slug(slug)
    if not template:
        raise APIError("Template not found.", 404)
    version = request.GET.get("version", "3.2.0")
    spec = generate_pull_endpoint_spec(template, version)
    return JsonResponse(spec)


@require_GET
@api_error_response
def pull_rest_docs(request, slug):
    """Serve Swagger UI for the template's generated spec."""
    template = _get_template_by_slug(slug)
    if not template:
        raise APIError("Template not found.", 404)
    version = request.GET.get("version", "3.2.0")
    return HttpResponse(get_swagger_ui_html(template.name, template.slug, version))


# ---------------------------------------------------------------------------
# GraphQL pull
# ---------------------------------------------------------------------------
@csrf_exempt
@safe_ratelimit(key="ip", rate=_rate_limit_config, block=False)
@require_http_methods(["GET", "POST"])
@api_error_response
def pull_graphql_endpoint(request, slug, dest_slug=None):
    """Serve the auto-generated GraphQL endpoint (playground + execution)."""
    limited = _maybe_rate_limited(request)
    if limited:
        return limited

    template = _get_template_by_slug(slug)
    if not template:
        raise APIError("Template not found.", 404)

    # Without a destination slug, redirect to the first destination (original behavior).
    if dest_slug is None:
        from apps.pull.services.strawberry_dynamic import _resolve_destination

        dest = _resolve_destination(template)
        first_slug = _dest_slug(dest.get("name"))
        return redirect(
            f"/api/v1/bridge/graphql/{slug}/{first_slug}/"
        )

    if request.method == "GET":
        # Playground is public (original parity): only data execution is authed.
        return HttpResponse(get_graphiql_html(template.name), content_type="text/html")

    # POST = data execution → enforce per-template bearer auth.
    auth_error = _check_client_auth(template, request)
    if auth_error:
        return auth_error

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise APIError("Invalid JSON body.", 400)

    query = body.get("query")
    if not query:
        raise APIError("GraphQL query is required.", 400)

    cached = _get_cached(f"{slug}:{dest_slug}", "graphql")
    if cached is not None and not body.get("variables"):
        return JsonResponse(cached)

    data, errors = execute_graphql(template, query, body.get("variables"), dest_slug=dest_slug)
    response: dict = {"data": data}
    if errors:
        response["errors"] = [
            {"message": str(e), "locations": getattr(e, "locations", None)} for e in errors
        ]
    if not errors:
        _set_cached(f"{slug}:{dest_slug}", "graphql", response)
    return JsonResponse(response)


def get_graphiql_html(title):
    """GraphiQL playground UI (served for GET /graphql/<slug>/)."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>GraphiQL - %s</title>
      <style>body{height:100%%;margin:0;width:100%%;overflow:hidden}#graphiql{height:100vh}</style>
      <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
      <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
      <link rel="stylesheet" href="https://unpkg.com/graphiql@3/graphiql.min.css" />
    </head>
    <body>
      <div id="graphiql">Loading GraphiQL...</div>
      <script crossorigin src="https://unpkg.com/graphiql@3/graphiql.min.js"></script>
      <script>
        const root = ReactDOM.createRoot(document.getElementById('graphiql'));
        root.render(React.createElement(GraphiQL, {
          fetcher: GraphiQL.createFetcher({ url: window.location.href, method: 'POST' }),
          defaultQuery: '{ data { } }',
        }));
      </script>
    </body>
    </html>
    """ % (title,)


# ---------------------------------------------------------------------------
# Engine helpers: GraphQL introspection + field-mapping test (original parity)
# ---------------------------------------------------------------------------
@api_error_response
@csrf_exempt
@require_http_methods(["POST"])
def graphql_introspect(request):
    """Introspect an external GraphQL endpoint (port of original /graphql_introspect).

    POST {url, auth_token} → returns the introspection schema JSON.
    """
    import json

    from apps.pull.services.graphql import introspect_graphql_endpoint

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise APIError("Invalid JSON body.", 400)

    url = body.get("url")
    if not url:
        raise APIError("URL is required.", 400)

    try:
        schema = introspect_graphql_endpoint(url, body.get("auth_token"))
        return JsonResponse(schema)
    except Exception as exc:
        raise APIError(str(exc), 500)


@api_error_response
@csrf_exempt
@require_http_methods(["POST"])
def test_mapping(request):
    """Preview the nested payload a field mapping produces (original parity).

    POST {mapping: [{source, target}]} → {sample_payload}. Values are shown as
    <Sample source> placeholders; the structure mirrors build_nested_payload.
    """
    import json

    from apps.core.services.data_transform import build_nested_payload

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise APIError("Invalid JSON body.", 400)

    mapping = body.get("mapping", [])
    if not isinstance(mapping, list):
        raise APIError("mapping must be a list.", 400)

    # Build a placeholder source dict so the shape is visible without real data.
    sample_source = {}
    for item in mapping:
        if isinstance(item, dict) and item.get("source"):
            sample_source[item["source"]] = f"<Sample {item['source']}>"

    payload = build_nested_payload(mapping, sample_source)
    return JsonResponse({"sample_payload": payload})


# ---------------------------------------------------------------------------
# Per-connection docs + GraphQL test pages (original /docs/<id> + /graphql/test/<id>)
# ---------------------------------------------------------------------------
@api_error_response
@require_GET
def connection_docs(request, connection_id):
    """Render Swagger UI for a connection's stored spec (original /docs/<id>)."""
    from apps.connections.models import Connection

    conn = Connection.objects.filter(pk=connection_id).first()
    if not conn:
        raise APIError("Connection not found.", 404)

    spec_text = conn.json_content or "{}"
    spec_url = f"/api/v1/connections/{conn.pk}/"
    return HttpResponse(
        _connection_swagger_html(conn.name, spec_text, spec_url),
        content_type="text/html",
    )


@api_error_response
@require_GET
def connection_graphql_test(request, connection_id):
    """Render a GraphiQL playground for a GraphQL connection (original parity)."""
    from apps.connections.models import Connection

    conn = Connection.objects.filter(pk=connection_id).first()
    if not conn:
        raise APIError("Connection not found.", 404)
    if conn.connection_type != "graphql":
        raise APIError("Not a GraphQL connection.", 400)
    return HttpResponse(
        _graphiql_html(conn.name, conn.url or ""),
        content_type="text/html",
    )


def _connection_swagger_html(name, spec_text, spec_url):
    """Swagger UI page rendering a connection's stored spec (no CDN fallback
    needed beyond unpkg — same as the original)."""
    import json

    try:
        parsed = json.loads(spec_text)
        embedded = json.dumps(parsed)
    except json.JSONDecodeError:
        embedded = "null"
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>Swagger UI - {name}</title>
      <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
      <style>html {{ box-sizing: border-box; overflow-y: scroll; }} body {{ margin: 0; background: #fafafa; }} .topbar {{ display: none !important; }}</style>
    </head>
    <body>
      <div id="swagger-ui"></div>
      <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
      <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" crossorigin></script>
      <script>
        const embedded = {embedded};
        if (!embedded || !embedded.swagger && !embedded.openapi) {{
          document.getElementById('swagger-ui').innerHTML =
            "<h2 style='color:orange;text-align:center;padding:20px;'>No valid API data found for this connection.</h2>";
        }} else {{
          window.ui = SwaggerUIBundle({{
            spec: embedded,
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
            layout: "BaseLayout",
          }});
        }}
      </script>
    </body>
    </html>
    """


def _graphiql_html(title, endpoint_url):
    """GraphiQL playground page (used for per-connection GraphQL test)."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>GraphiQL - {title}</title>
      <style>body{{height:100vh;margin:0;overflow:hidden}}#graphiql{{height:100vh}}</style>
      <link rel="stylesheet" href="https://unpkg.com/graphiql@3/graphiql.min.css" />
    </head>
    <body>
      <div id="graphiql">Loading GraphiQL...</div>
      <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
      <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
      <script crossorigin src="https://unpkg.com/graphiql@3/graphiql.min.js"></script>
      <script>
        const root = ReactDOM.createRoot(document.getElementById('graphiql'));
        root.render(React.createElement(GraphiQL, {{
          fetcher: GraphiQL.createFetcher({{ url: {json.dumps(endpoint_url or '')} }}),
          defaultQuery: '{{ data {{ }} }}',
        }}));
      </script>
    </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Mock server
# ---------------------------------------------------------------------------
@require_GET
@api_error_response
def mock_server(request, connection_id, path):
    """Serve example JSON from a connection's OpenAPI spec (original parity).

    Handles {param} path segments and Swagger 2.0 `examples` / OpenAPI 3
    `content.example(s)` response values.
    """
    from apps.connections.models import Connection

    conn = Connection.objects.filter(pk=connection_id).first()
    if not conn:
        raise APIError("Connection not found.", 404)

    try:
        spec = json.loads(conn.json_content) if conn.json_content else {}
    except json.JSONDecodeError:
        raise APIError("Connection spec is not valid JSON.", 500)

    paths = spec.get("paths", {})
    target = None
    request_path = path.rstrip("/")
    for spec_path, operations in paths.items():
        if _path_matches(spec_path, request_path):
            target = operations
            break

    if not target:
        return JsonResponse(
            {"status": "error", "message": f"No example found for path: /{path}", "code": 404},
            status=404,
        )

    # Prefer GET response example; fall back to first operation.
    op = target.get("get") or next(iter(target.values()), None)
    if not op:
        return JsonResponse({"status": "error", "message": "No operations for path.", "code": 404}, status=404)

    responses = op.get("responses", {})
    success = responses.get("200") or responses.get("2XX") or {}
    example = _extract_example(success)
    if example is not None:
        return JsonResponse(example)

    return JsonResponse({"status": "ok", "path": f"/{path}", "message": "No example defined in spec."})


def _normalize_path(p):
    """Convert OpenAPI {param} paths into a comparable form."""
    import re

    return re.sub(r"\{[^}]+\}", "", p).rstrip("/")


def _path_matches(spec_path, request_path):
    """Match a request path against an OpenAPI path template.

    `/users/{id}` matches `/users/42`; literal segments must be equal.
    Leading slashes are normalized (the URL path converter strips them).
    """
    import re

    normalized_spec = spec_path.rstrip("/").lstrip("/")
    normalized_req = request_path.rstrip("/").lstrip("/")
    pattern = re.sub(r"\{[^}]+\}", r"[^/]+", normalized_spec)
    regex = re.compile(rf"^{pattern}$")
    return bool(regex.match(normalized_req))


def _extract_example(response_def):
    """Extract an example value from an OpenAPI 2.0/3.x response definition."""
    if not isinstance(response_def, dict):
        return None
    if "examples" in response_def and isinstance(response_def["examples"], dict):
        ex = response_def["examples"].get("application/json")
        return ex
    content = response_def.get("content", {})
    media = content.get("application/json", {})
    if "example" in media:
        return media["example"]
    examples = media.get("examples", {})
    if examples:
        first = next(iter(examples.values()), {})
        if isinstance(first, dict):
            return first.get("value")
    return None
