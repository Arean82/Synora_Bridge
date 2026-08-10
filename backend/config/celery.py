"""
Celery application for Synora Bridge.

Broker/result backend default to Redis (Memurai on Windows) via environment
variables. `CELERY_TASK_ALWAYS_EAGER` forces inline execution in tests.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("synora_bridge")

# Read broker/backend from Django settings (config.settings.base → env).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from installed apps.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
