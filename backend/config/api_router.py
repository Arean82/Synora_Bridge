"""
API router aggregation — the single place that composes every feature domain's
routers into one `/api/v1/` namespace. Adding a new feature = register its
router here and in INSTALLED_APPS; nothing else changes.
"""
from rest_framework.routers import DefaultRouter

from apps.connections.api import router as connections_router
from apps.configs.api import router as configs_router
from apps.core.api import router as core_router
from apps.core.api import urlpatterns as core_urlpatterns
from apps.jobs.api import router as jobs_router
from apps.observability.api import urlpatterns as observability_urlpatterns
from apps.pull.api import urlpatterns as pull_urlpatterns

# Project-wide router: all domain routers merge into one URL space.
router = DefaultRouter()
router.registry.extend(configs_router.registry)
router.registry.extend(connections_router.registry)
router.registry.extend(jobs_router.registry)
router.registry.extend(core_router.registry)

# Observability, pull + core expose plain URL patterns (health/metrics,
# dynamic pull endpoints/mock server, config read/write), not routers.
urlpatterns = (
    router.urls
    + observability_urlpatterns
    + pull_urlpatterns
    + core_urlpatterns
)
