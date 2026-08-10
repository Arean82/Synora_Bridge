"""
Job model signals — keep django-celery-beat in sync with job lifecycle.

Fires on Job post_save / post_delete so the DatabaseScheduler schedule always
reflects the DB (equivalent of the Flask app re-registering APScheduler jobs
at startup and on toggle).
"""
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="jobs.Job")
def job_saved(sender, instance, **kwargs):
    from apps.jobs.beat import sync_job_to_beat

    try:
        sync_job_to_beat(instance)
    except Exception:
        logger.exception("Failed to sync job %s to beat on save", instance.pk)


@receiver(post_delete, sender="jobs.Job")
def job_deleted(sender, instance, **kwargs):
    from apps.jobs.beat import remove_job_from_beat

    try:
        remove_job_from_beat(instance.pk)
    except Exception:
        logger.exception("Failed to remove job %s from beat on delete", instance.pk)
