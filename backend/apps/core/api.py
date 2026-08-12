"""Core domain router + plain URL patterns."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.core.views import AppSettingViewSet, AuditLogViewSet
from apps.core.views_config import (
    config_endpoint,
    doc_content,
    email_template_detail,
    email_templates_list,
    restart_endpoint,
    verify_db_endpoint,
)

router = DefaultRouter()
router.register("settings", AppSettingViewSet, basename="setting")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")

urlpatterns = [
    # System Configuration (config.ini read/write) — full GUI support.
    path("config/", config_endpoint, name="config"),
    # PostgreSQL connection test (stateless — used by the Settings GUI before
    # switching [Server] database to postgresql).
    path("config/verify-db/", verify_db_endpoint, name="config-verify-db"),
    # One-click restart (daphne re-executes itself in place; validated).
    path("config/restart/", restart_endpoint, name="config-restart"),
    # Documentation viewer (README.md + docs/*.md) — original docs modal parity.
    path("docs/markdown/<path:filename>/", doc_content, name="doc-content"),
    # Email template management (failure alerts).
    path("email-templates/", email_templates_list, name="email-templates-list"),
    path("email-templates/<path:filename>/", email_template_detail, name="email-template-detail"),
]
