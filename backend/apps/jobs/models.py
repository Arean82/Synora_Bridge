"""Jobs domain models — scheduled executions, run logs, failed payloads."""
from django.db import models

from apps.core.fields import EncryptedJSONField


class Job(models.Model):
    """A scheduled execution of a bridge template."""

    template = models.ForeignKey(
        "configs.Template",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    schedule_interval = models.IntegerField(default=60)  # seconds
    is_active = models.BooleanField(default=True)

    last_run = models.DateTimeField(blank=True, null=True)
    last_status = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job #{self.pk} ({self.template.name})"


class JobLog(models.Model):
    """Outcome record for a single job execution."""

    STATUS_CHOICES = [("SUCCESS", "Success"), ("FAILED", "Failed")]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="logs")
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    http_status = models.IntegerField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    payload_json = EncryptedJSONField(blank=True, null=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"JobLog #{self.pk} [{self.status}]"


class FailedPayload(models.Model):
    """Payload that failed to be delivered to a destination."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="failed_payloads")
    template = models.ForeignKey(
        "configs.Template",
        on_delete=models.CASCADE,
        related_name="failed_payloads",
    )
    payload_json = EncryptedJSONField()
    error_message = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"FailedPayload #{self.pk} (Job {self.job.pk})"
