"""Observability domain router (health + metrics)."""
from django.urls import path

from apps.observability.views import health, liveness_probe, metrics, readiness_probe

urlpatterns = [
    path("health/live/", liveness_probe, name="health-live"),
    path("health/ready/", readiness_probe, name="health-ready"),
    path("health/", health, name="health"),
    path("metrics/", metrics, name="metrics"),
]
