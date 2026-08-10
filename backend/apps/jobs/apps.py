from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jobs"
    verbose_name = "Scheduled Jobs"

    def ready(self):
        # Register beat-sync signals.
        from apps.jobs import signals  # noqa: F401
