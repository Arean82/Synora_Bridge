"""
Root URL configuration for Synora Bridge.

Every feature domain owns its URLs inside its app module (`apps/<name>/urls.py`)
and is mounted here with a clear prefix:
- /api/v1/...   → DRF REST API (apps.*.api + core)
- /graphql/...  → Strawberry GraphQL
- /ws/...       → Channels WebSocket routes (see config.asgi)
- /admin/       → Django admin
- /schema/      → drf-spectacular OpenAPI schema + Swagger UI/ReDoc
"""
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # REST API v1 — each app registers its own router under this prefix.
    path("api/v1/", include("config.api_router")),
    # drf-spectacular OpenAPI schema (the generated clients' source of truth)
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="schema-swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="schema-redoc"),
]
