from django.apps import AppConfig


class PullConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pull"
    verbose_name = "Pull Modes (REST & GraphQL)"
