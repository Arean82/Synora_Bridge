"""Configs domain router."""
from rest_framework.routers import DefaultRouter

from apps.configs.views import TemplateViewSet

router = DefaultRouter()
router.register("templates", TemplateViewSet, basename="template")
