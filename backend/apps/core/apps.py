"""Core AppConfig — startup hooks (OTel instrumentation)."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core (shared services & settings)"

    def ready(self):
        from apps.core.services.otel import setup_otel

        setup_otel()
