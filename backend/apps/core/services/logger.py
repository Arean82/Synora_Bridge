"""
Audit + job logging services — the Universal Audit Engine.

Ports Flask `bridge_app/services/logger.py`:
- log_job: record a job execution outcome (JobLog)
- log_audit: record every data transaction (AuditLog)
"""
import logging
import uuid

from django.utils import timezone

logger = logging.getLogger(__name__)


def log_job(job_id, status, payload, http_status=None, error_message=None):
    """Record the outcome of a push job execution."""
    from apps.jobs.models import Job, JobLog

    try:
        job = Job.objects.filter(pk=job_id).first()
        if job:
            # Store an aware datetime (USE_TZ=True) for the app timezone.
            job.last_run = timezone.now()
            job.last_status = status
            job.save(update_fields=["last_run", "last_status", "updated_at"])

        JobLog.objects.create(
            job_id=job_id,
            status=status,
            http_status=http_status,
            error_message=error_message,
            payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to write job log for job %s", job_id)


def log_audit(mode, caller, payload, endpoint=None, template_id=None, status="SUCCESS"):
    """Log every data transaction to the Universal Audit Engine."""
    from apps.core.models import AuditLog

    try:
        payload_bytes = len(__import__("json").dumps(payload).encode("utf-8")) if payload else 0
        if isinstance(payload, list):
            record_count = len(payload)
        elif isinstance(payload, dict) and payload.get("data"):
            record_count = len(payload["data"].values())
        else:
            record_count = 1

        AuditLog.objects.create(
            transaction_id=uuid.uuid4(),
            mode=mode,
            caller=caller,
            bytes_transferred=payload_bytes,
            record_count=record_count,
            status=status,
            endpoint=endpoint,
            template_id=template_id,
            payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to write audit log")
