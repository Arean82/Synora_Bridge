"""
Configs domain models — the bridge execution template.

Faithful port of original `TemplateModel`: a template defines the sources to pull
from, the destinations to push to, field mappings, and the execution mode
(push / pull_rest / pull_graphql). Sensitive JSON payloads (sources contain
auth tokens, destinations contain credentials) are encrypted at rest.
"""
import re

from django.conf import settings
from django.db import models
from timezone_field import TimeZoneField

from apps.core.fields import EncryptedJSONField, EncryptedTextField


class Template(models.Model):
    """A bridge configuration template (source â†’ mapping â†’ destinations)."""

    EXECUTION_MODES = [
        ("push", "Push"),
        ("pull_rest", "Pull REST"),
        ("pull_graphql", "Pull GraphQL"),
    ]

    name = models.CharField(max_length=100, unique=True)

    # Stored, indexed URL slug (scale item: O(1) pull-endpoint routing instead
    # of a full-table Python scan on every pull request).
    slug = models.SlugField(max_length=120, unique=True, db_index=True, blank=True)

    execution_mode = models.CharField(max_length=50, choices=EXECUTION_MODES, default="push")
    pull_method = models.CharField(max_length=10, default="GET")

    # Per-template timezone (IANA zone). Defaults to the global
    # [Server] timezone from config.ini; changeable per template via the API.
    timezone = TimeZoneField(default=settings.TIME_ZONE)

    # --- Partner (source) config ---
    # Legacy single-endpoint fields (kept for backward compatibility with the
    # original data model; new templates use `sources`).
    partner_url = models.CharField(max_length=255, blank=True, null=True)
    partner_auth_token = EncryptedTextField(blank=True, null=True)

    # Array of {name, url, auth_token, method, source_type, graphql_query}
    sources = EncryptedJSONField(default=list, blank=True)

    # --- Client (destination) config ---
    client_name = models.CharField(max_length=100, blank=True, null=True)
    client_url = models.CharField(max_length=255, blank=True, null=True)
    client_auth_type = models.CharField(max_length=50, default="none")

    # {token, email, password, timeout, retries} for client auth
    client_credentials = EncryptedJSONField(default=dict, blank=True)

    # Array of {name, url, method, auth_type, credentials, field_mapping}
    destinations = EncryptedJSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bridge Template"
        verbose_name_plural = "Bridge Templates"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate the indexed slug from the template name."""
        if not self.slug:
            base = re.sub(r"[^a-zA-Z0-9]+", "_", self.name).strip("_").lower()
            self.slug = base or "template"
        super().save(*args, **kwargs)
