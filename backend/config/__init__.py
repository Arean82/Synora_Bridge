"""
Synora Bridge — Django project package.

The project lives in `config/`; feature code lives in modular `apps/`.
Settings are split: config.settings.base + environment-specific module.

Importing the Celery app here is the canonical Django+Celery pattern: it
ensures `config.celery.app` is configured (broker from config.ini, eager flag,
beat scheduler) before any shared_task is bound, so tasks never fall back to
Celery's unconfigured default app.
"""
from .celery import app as celery_app

__all__ = ("celery_app",)
