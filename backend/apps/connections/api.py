"""Connections domain router."""
from rest_framework.routers import DefaultRouter

from apps.connections.views import ConnectionViewSet

router = DefaultRouter()
router.register("connections", ConnectionViewSet, basename="connection")
