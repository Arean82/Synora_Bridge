"""Core domain router + plain URL patterns."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.core.views import AppSettingViewSet, AuditLogViewSet
from apps.core.views_config import (
    config_endpoint,
    doc_content,
    email_template_detail,
    email_templates_list,
)

router = DefaultRouter()
router.register("settings", AppSettingViewSet, basename="setting")
router.register("audit-logs", AuditLogViewSet, basename="auditlog")

urlpatterns = [
    # System Configuration (config.ini read/write) — full GUI support.
    path("config/", config_endpoint, name="config"),
    # Documentation viewer (README.md + docs/*.md) — original docs modal parity.
    path("docs/markdown/<path:filename>/", doc_content, name="doc-content"),
    # Email template management (failure alerts).
    path("email-templates/", email_templates_list, name="email-templates-list"),
    path("email-templates/<path:filename>/", email_template_detail, name="email-template-detail"),
]
