"""Management command: reconcile the Celery beat schedule from the jobs table.

Usage: python manage.py sync_beat
Runs automatically at app startup (guarded) and is safe to run manually
after bulk data imports or restores.
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile django-celery-beat schedule with Job records + system tasks."

    def handle(self, *args, **options):
        from apps.jobs.beat import ensure_system_tasks, sync_all_jobs_to_beat

        ensure_system_tasks()
        sync_all_jobs_to_beat()
        self.stdout.write(self.style.SUCCESS("Beat schedule reconciled."))
