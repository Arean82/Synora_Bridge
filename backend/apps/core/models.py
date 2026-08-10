"""Core domain models â€” app settings and the universal audit log."""
import uuid

from django.db import models


class AppSetting(models.Model):
    """Key/value application settings (UI theme, layout, date format, etc.).

    Replaces the original `config.ini [UI]` section: editable at runtime via the
    settings API instead of editing a file.
    """

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class AuditLog(models.Model):
    """Universal Audit Engine â€” records every data transaction.

    Ports original `AuditLog`: every push / pull-rest / pull-graphql transaction
    with transaction id, caller, bytes transferred, record count and status.
    """

    MODE_CHOICES = [
        ("PUSH", "Push"),
        ("PULL_REST", "Pull REST"),
        ("PULL_GRAPHQL", "Pull GraphQL"),
        ("WEBSOCKET", "WebSocket"),
    ]

    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    caller = models.CharField(max_length=100)  # IP, job id, or API key
    bytes_transferred = models.IntegerField(default=0)
    record_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="SUCCESS")
    timestamp = models.DateTimeField(auto_now_add=True)
    payload_json = models.JSONField(blank=True, null=True)
    endpoint = models.CharField(max_length=255, blank=True, null=True)
    template = models.ForeignKey(
        "configs.Template",
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"AuditLog {self.transaction_id} [{self.mode}]"
