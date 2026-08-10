"""Pull domain URL patterns (REST/GraphQL endpoints + mock server).

These are mounted under /api/v1/bridge/... by config.api_router.
"""
from django.urls import path

from apps.pull import views

urlpatterns = [
    # Auto-generated pull REST endpoint + docs/spec
    path("bridge/pull/<slug:slug>/<slug:dest_slug>/", views.pull_rest_endpoint, name="pull-rest-endpoint"),
    path("bridge/pull/<slug:slug>/spec", views.pull_rest_spec, name="pull-rest-spec"),
    path("bridge/pull/<slug:slug>/docs", views.pull_rest_docs, name="pull-rest-docs"),
    # Auto-generated pull GraphQL endpoint (POST executes, GET renders playground).
    # Dest-specific variant + redirect for the bare slug (original parity).
    path("bridge/graphql/<slug:slug>/<slug:dest_slug>/", views.pull_graphql_endpoint, name="pull-graphql-dest"),
    path("bridge/graphql/<slug:slug>/", views.pull_graphql_endpoint, name="pull-graphql"),
    # Engine helpers (original parity)
    path("bridge/graphql_introspect/", views.graphql_introspect, name="graphql-introspect"),
    path("test_mapping/", views.test_mapping, name="test-mapping"),
    # Per-connection docs + GraphQL test pages (original /docs/<id>, /graphql/test/<id>)
    path("docs/<int:connection_id>/", views.connection_docs, name="connection-docs"),
    path("graphql/test/<int:connection_id>/", views.connection_graphql_test, name="connection-graphql-test"),
    # Mock server: /api/v1/mock/<connection_id>/<path>
    path("mock/<int:connection_id>/<path:path>", views.mock_server, name="mock-server"),
]
