"""
Audit + job logging services — the Universal Audit Engine.

Ports original `bridge_app/services/logger.py`:
- log_job: record a job execution outcome (JobLog)
- log_audit: record every data transaction (AuditLog)
"""
import logging
import uuid

from django.utils import timezone

logger = logging.getLogger(__name__)


def log_job(job_id, status, payload, http_status=None, error_message=None):
    """Record the outcome of a push job execution.

    Best-effort by design: never raises and never prints a traceback — job
    execution must not depend on job-log persistence succeeding.
    """
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
            payload_json=_json_safe(payload),
        )
    except Exception as exc:
        logger.warning("Could not write job log for job %s: %s", job_id, exc)


def _json_safe(payload):
    """Return a JSON-serializable payload, falling back to ``str()`` when the
    payload contains non-serializable objects (datetimes, Decimals, ...).
    Never raises."""
    if payload is None:
        return None
    try:
        __import__("json").dumps(payload)
        return payload
    except (TypeError, ValueError):
        return str(payload)


def _payload_bytes(payload):
    """UTF-8 byte size of a JSON payload; never raises."""
    safe = _json_safe(payload)
    if safe is None:
        return 0
    return len(__import__("json").dumps(safe).encode("utf-8"))


def _record_count(payload):
    """Best-effort transaction record count for an audit payload.

    Payloads may be a list of records, a dict whose ``data`` value is a list
    of records (the shape push jobs produce), a dict whose ``data`` value is a
    dict, or a scalar. Never raises; returns at least 1.
    """
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return len(data.values())
    return 1


def log_audit(mode, caller, payload, endpoint=None, template_id=None, status="SUCCESS"):
    """Log every data transaction to the Universal Audit Engine.

    Best-effort by design: never raises and never prints a traceback — payload
    delivery must not depend on audit-log persistence succeeding.
    """
    from apps.core.models import AuditLog

    try:
        AuditLog.objects.create(
            transaction_id=uuid.uuid4(),
            mode=mode,
            caller=caller,
            bytes_transferred=_payload_bytes(payload),
            record_count=_record_count(payload),
            status=status,
            endpoint=endpoint,
            template_id=template_id,
            payload_json=_json_safe(payload),
        )
    except Exception as exc:
        logger.warning("Could not write audit log: %s", exc)
