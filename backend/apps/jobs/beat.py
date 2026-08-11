"""
Beat sync — keep django-celery-beat PeriodicTasks in sync with Job records.

The original original app restored active jobs into APScheduler at startup and
toggled them on the fly. With Django + django-celery-beat (DatabaseScheduler),
each active Job maps to one IntervalSchedule + PeriodicTask; signals keep the
schedule current on create/update/delete/toggle without any manual step.
"""
import logging

from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

logger = logging.getLogger(__name__)

# PeriodicTask name prefix for per-job schedules.
JOB_TASK_PREFIX = "bridge-job-"

# Fixed name for the periodic system tasks.
CLEANUP_TASK_NAME = "bridge-cleanup-failed-payloads"
SWAGGER_REFRESH_TASK_NAME = "bridge-swagger-refresh"


def _upsert_interval_schedule(seconds):
    """Get-or-create an IntervalSchedule for the given period in seconds."""
    # IntervalSchedule.period is a string code in ('seconds','minutes','hours','days','weeks').
    if seconds % 86400 == 0:
        period, every = "days", seconds // 86400
    elif seconds % 3600 == 0:
        period, every = "hours", seconds // 3600
    elif seconds % 60 == 0:
        period, every = "minutes", seconds // 60
    else:
        period, every = "seconds", seconds

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=every,
        period=period,
    )
    return schedule


def sync_job_to_beat(job):
    """Create/update the PeriodicTask for a job according to its state."""
    name = f"{JOB_TASK_PREFIX}{job.pk}"
    PeriodicTask.objects.filter(name=name).delete()

    if not job.is_active:
        return None

    schedule = _upsert_interval_schedule(max(1, job.schedule_interval))
    return PeriodicTask.objects.create(
        name=name,
        task="apps.jobs.tasks.pull_and_push_job",
        interval=schedule,
        args=f"[{job.pk}]",
        enabled=True,
    )


def remove_job_from_beat(job_id):
    """Remove the PeriodicTask for a deleted job."""
    PeriodicTask.objects.filter(name=f"{JOB_TASK_PREFIX}{job_id}").delete()


def sync_all_jobs_to_beat():
    """Rebuild the whole beat schedule from the jobs table (startup reconciliation)."""
    from apps.jobs.models import Job

    PeriodicTask.objects.filter(name__startswith=JOB_TASK_PREFIX).delete()
    for job in Job.objects.filter(is_active=True):
        try:
            sync_job_to_beat(job)
        except Exception:
            logger.exception("Failed to sync job %s to beat", job.pk)


# ---------------------------------------------------------------------------
# Fixed system periodic tasks
# ---------------------------------------------------------------------------
def _get_or_create_minute_interval(minutes):
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=minutes,
        period="minutes",
    )
    return schedule


def _get_or_create_hourly_interval(hours):
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=hours,
        period="hours",
    )
    return schedule


def ensure_system_tasks():
    """Ensure the periodic cleanup + swagger-refresh tasks exist (idempotent).

    Uses update-or-create so manual tuning (enabled flag, schedule tweaks) is
    preserved across app restarts.
    """
    cleanup_schedule = _get_or_create_minute_interval(5)
    PeriodicTask.objects.update_or_create(
        name=CLEANUP_TASK_NAME,
        defaults={
            "task": "apps.jobs.tasks.cleanup_failed_payloads",
            "interval": cleanup_schedule,
            "enabled": True,
        },
    )

    swagger_schedule = _get_or_create_hourly_interval(1)
    PeriodicTask.objects.update_or_create(
        name=SWAGGER_REFRESH_TASK_NAME,
        defaults={
            "task": "apps.connections.tasks.refresh_swagger_connections",
            "interval": swagger_schedule,
            "enabled": True,
        },
    )
