"""
Connections domain Celery tasks — background spec refresh.

Ports original `bridge_app/services/swagger_utils.py::update_swagger_connections`:
periodically re-fetch Swagger/OpenAPI JSON for remote connections, respecting
each connection's individual sync_schedule.
"""
import logging
from datetime import timedelta

import requests
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="apps.connections.tasks.refresh_swagger_connections")
def refresh_swagger_connections():
    """Refresh spec content for remote (non-local-file) connections."""
    from apps.connections.models import Connection

    updated, failed = 0, 0
    for conn in Connection.objects.filter(is_local_file=False):
        if not conn.url:
            continue

        # Respect individual sync_schedule cooldown.
        if conn.sync_schedule and conn.last_updated:
            now = timezone.now()
            if conn.sync_schedule == "hourly" and (now - conn.last_updated) < timedelta(hours=1):
                continue
            if conn.sync_schedule == "daily" and (now - conn.last_updated) < timedelta(days=1):
                continue
            if conn.sync_schedule == "weekly" and (now - conn.last_updated) < timedelta(weeks=1):
                continue

        try:
            from apps.connections.services import fetch_swagger_json

            json_data, _ = fetch_swagger_json(conn.url, timeout=10)
            import json as _json

            conn.json_content = (
                _json.dumps(json_data) if isinstance(json_data, dict) else json_data
            )
            conn.last_updated = timezone.now()
            conn.save(update_fields=["json_content", "last_updated"])
            updated += 1
        except Exception:
            failed += 1
            logger.exception("Error updating SwaggerConnection %s", conn.name)

    logger.info("Swagger refresh done: %s updated, %s failed", updated, failed)
    return {"updated": updated, "failed": failed}
