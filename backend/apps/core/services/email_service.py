"""
Email alert service â€” dispatch failure alerts with throttling.

Ports original `bridge_app/services/email_service.py`: modes none|local|smtp,
per-job cooldown throttle, HTML failure template. Uses Django's email
infrastructure.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

# In-memory throttle: {job_id: last_sent_datetime}
_last_email_sent: dict = {}


def should_throttle(job_id) -> bool:
    """True if an email for this job should be suppressed (cooldown active)."""
    try:
        if not settings.EMAIL_THROTTLE_ENABLED:
            return False
        last = _last_email_sent.get(job_id)
        if last and (timezone.now() - last) < timedelta(minutes=settings.EMAIL_THROTTLE_MINUTES):
            return True
        _last_email_sent[job_id] = timezone.now()
        return False
    except Exception:
        logger.exception("Error checking email throttle")
        return False


def send_failure_alert(job_id, template_name, dest_url, error_msg):
    """Dispatch an email alert if [EMAIL] mode is configured."""
    mode = settings.EMAIL_MODE
    if mode in (None, "", "none"):
        return

    if should_throttle(job_id):
        logger.info("Email alert for Job %s throttled (cooldown active).", job_id)
        return

    recipients = settings.EMAIL_RECIPIENTS
    if not recipients:
        logger.info("Email service is active but no recipients configured.")
        return

    subject = f"Alert: Schedule Job {job_id} ({template_name}) Failed"
    try:
        html_content = render_to_string(
            "email/failure_alert.html",
            {
                "job_id": job_id,
                "template_name": template_name,
                "dest_url": dest_url,
                "error_msg": error_msg,
                "timestamp": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    except Exception:
        logger.exception("Error rendering email template")
        html_content = (
            f"<h2>Schedule Failure Alert</h2><p>Job ID: {job_id}</p><pre>{error_msg}</pre>"
        )

    message = EmailMultiAlternatives(
        subject=subject,
        body="Please view this email in an HTML compatible client.",
        from_email=settings.EMAIL_SENDER,
        to=recipients,
    )
    message.attach_alternative(html_content, "text/html")

    try:
        message.send(fail_silently=False)
        logger.info("Sent failure alert for Job %s", job_id)
    except Exception:
        logger.exception("Failed to send failure alert email for Job %s", job_id)
