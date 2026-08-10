"""Core domain router + plain URL patterns."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.core.views import AppSettingViewSet, AuditLogViewSet
from apps.core.views_config import config_endpoint

router = DefaultRouter()
router.register("settings", AppSettingViewSet, basename="setting")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")

urlpatterns = [
    # System Configuration (config.ini read/write) — full GUI support.
    path("config/", config_endpoint, name="config"),
]
