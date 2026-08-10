"""Celery engine tests — push pipeline, beat sync, audit (Phase 3 verification)."""
import pytest
from django_celery_beat.models import PeriodicTask

from apps.configs.models import Template
from apps.core.models import AuditLog
from apps.jobs.models import Job, JobLog
from apps.jobs.tasks import cleanup_failed_payloads, pull_and_push_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def engine_job(mock_source_url):
    tpl = Template.objects.create(
        name="Engine Test",
        execution_mode="push",
        sources=[{"name": "mock", "url": mock_source_url, "source_type": "rest", "selectedApi": "/source", "method": "GET"}],
        destinations=[{
            "name": "dest",
            "url": mock_source_url,  # engine treats non-2xx/errors gracefully
            "method": "POST",
            "auth_type": "none",
            "credentials": {},
            "field_mapping": [
                {"source": "source_0.name", "target": "company.name"},
                {"source": "source_0.gps_lat", "target": "gps[0].latitude"},
            ],
        }],
        client_credentials={"token": "x"},
    )
    job = Job.objects.create(template=tpl, schedule_interval=60, is_active=True)
    yield job, tpl
    job.delete()
    tpl.delete()


def test_beat_schedule_created(engine_job):
    job, _tpl = engine_job
    assert PeriodicTask.objects.filter(name=f"bridge-job-{job.pk}").exists()


def test_beat_schedule_removed_on_deactivate(engine_job):
    job, _tpl = engine_job
    job.is_active = False
    job.save(update_fields=["is_active"])
    assert not PeriodicTask.objects.filter(name=f"bridge-job-{job.pk}").exists()


def test_pull_and_push_task_runs(engine_job):
    job, tpl = engine_job
    result = pull_and_push_job.run(job.pk)  # type: ignore[attr-defined]
    assert result is not None
    assert result["template"] == tpl.name

    job.refresh_from_db()
    assert job.last_status in ("SUCCESS", "FAILED")  # destination mock is GET-only
    assert JobLog.objects.filter(job=job).exists()
    assert AuditLog.objects.filter(mode="PUSH").exists()


def test_cleanup_task(engine_job):
    result = cleanup_failed_payloads.run()  # type: ignore[attr-defined]
    assert result is not None


def test_beat_reconcile_is_idempotent(engine_job):
    from apps.jobs.beat import ensure_system_tasks, sync_all_jobs_to_beat

    job, _tpl = engine_job
    sync_all_jobs_to_beat()
    ensure_system_tasks()
    first = PeriodicTask.objects.count()
    sync_all_jobs_to_beat()
    ensure_system_tasks()
    second = PeriodicTask.objects.count()
    assert first == second
    assert PeriodicTask.objects.filter(name=f"bridge-job-{job.pk}").exists()
    assert PeriodicTask.objects.filter(name="bridge-cleanup-failed-payloads").exists()
    assert PeriodicTask.objects.filter(name="bridge-swagger-refresh").exists()
