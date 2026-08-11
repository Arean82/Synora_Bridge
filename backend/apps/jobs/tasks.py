"""
Celery tasks — the push/pull execution engine.

Ports original `bridge_app/services/task_runner.py`:

- pull_and_push_job(job_id): fetch all sources concurrently â†’ aggregate with
  source_N. prefixes â†’ transform per destination mapping â†’ push with retry +
  auth flows â†’ audit + failed-payload capture + email alerts + WebSocket feed.
- execute_template_mapping(template_id, dest_slug): pull-mode variant that
  fetches sources and returns the transformed payload without pushing.
- cleanup_failed_payloads(): prune expired failed payloads.
"""
import concurrent.futures
import logging
import re
from urllib.parse import urlparse

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source fetching
# ---------------------------------------------------------------------------
def _fetch_source_data(idx, src):
    """Fetch one source endpoint; returns {source_<idx>.<field>: value}."""
    src_url = src.get("url")
    if not src_url:
        return {}
    src_auth = src.get("auth_token")
    src_method = src.get("method", "GET").upper()
    source_type = src.get("source_type", "rest")

    local_aggregated = {}
    try:
        if source_type == "graphql":
            from apps.pull.services.graphql import fetch_from_graphql_source

            query = src.get("graphql_query")
            data = fetch_from_graphql_source(src_url, query, src_auth)
            src_data = data[0] if isinstance(data, list) else data
        else:
            headers = {}
            if src_auth:
                headers["Authorization"] = f"Bearer {src_auth}"
            res = requests.request(src_method, src_url, headers=headers, timeout=10)
            if res.status_code != 200:
                logger.warning("Source %s (%s %s) returned %s", idx, src_method, src_url, res.status_code)
                return {}
            data = res.json()
            src_data = data[0] if isinstance(data, list) else data

        for k, v in src_data.items():
            local_aggregated[f"source_{idx}.{k}"] = v
    except Exception:
        logger.exception("Failed to fetch source %s (%s)", idx, src_url)

    return local_aggregated


def fetch_all_sources(template):
    """Concurrently fetch all sources of a template; return flat aggregate dict."""
    sources = template.sources or []
    # Backward compatibility: legacy single partner endpoint.
    if not sources and template.partner_url:
        sources = [
            {
                "name": "Legacy",
                "url": template.partner_url,
                "auth_token": template.partner_auth_token,
            }
        ]

    aggregated_data = {}
    if not sources:
        return aggregated_data

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {
            executor.submit(_fetch_source_data, idx, src): idx
            for idx, src in enumerate(sources)
        }
        for future in concurrent.futures.as_completed(futures):
            aggregated_data.update(future.result())

    return aggregated_data


def _resolve_destination(template, dest_slug=None):
    """Find a destination by slug, or fall back to the first."""
    destinations = template.destinations or []
    if not destinations:
        return None, []

    if dest_slug:
        for dest in destinations:
            d_slug = re.sub(r"[^a-z0-9]", "_", dest.get("name", "").lower())
            if d_slug == dest_slug:
                return dest, dest.get("field_mapping", [])
        return None, []

    return destinations[0], destinations[0].get("field_mapping", [])


def _build_dest_session(dest):
    """Create a requests.Session with retry strategy for a destination."""
    creds = dest.get("credentials", {})
    req_retries = int(creds.get("retries", 3))

    session = requests.Session()
    retry_strategy = Retry(
        total=req_retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "PUT", "PATCH", "DELETE", "GET"],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _authenticate_destination(dest, dest_headers):
    """Apply destination auth (bearer / custom_login); returns error string or None."""
    auth_type = dest.get("auth_type", "none")
    creds = dest.get("credentials", {})
    dest_url = dest.get("url", "")

    if auth_type == "custom_login":
        email = creds.get("email")
        password = creds.get("password")
        parsed = urlparse(dest_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        auth_url = f"{base_url}/api/v1/login"
        try:
            auth_res = requests.post(
                auth_url, json={"email": email, "password": password}, timeout=10
            )
            if auth_res.status_code != 200:
                return f"Auth Failed for {dest_url}"
            token = auth_res.json().get("token")
            dest_headers["Authorization"] = f"Bearer {token}"
        except Exception as exc:
            return f"Auth Request Failed for {dest_url}: {exc}"
    elif auth_type == "bearer":
        token = creds.get("token")
        if token:
            dest_headers["Authorization"] = f"Bearer {token}"

    return None


def _push_to_destination(job, template, dest, payload):
    """Push a payload to one destination; returns (status_flag, http_status, error)."""
    from apps.core.services.email_service import send_failure_alert
    from apps.core.services.logger import log_audit, log_job

    dest_url = dest.get("url")
    if not dest_url:
        return "SKIPPED", None, None

    dest_method = dest.get("method", "POST").upper()
    dest_headers = {"Content-Type": "application/json"}

    auth_error = _authenticate_destination(dest, dest_headers)
    if auth_error:
        log_job(job.id, "FAILED", payload, http_status=401, error_message=auth_error)
        send_failure_alert(job.id, template.name, dest_url, auth_error)
        return "FAILED", 401, auth_error

    creds = dest.get("credentials", {})
    req_timeout = int(creds.get("timeout", 30))
    session = _build_dest_session(dest)

    try:
        dest_res = session.request(
            dest_method, dest_url, json=payload, headers=dest_headers, timeout=req_timeout
        )
        status_flag = "SUCCESS" if dest_res.status_code < 400 else "FAILED"

        log_audit(
            mode="PUSH",
            caller=f"Job-{job.id}",
            payload=payload,
            endpoint=dest_url,
            template_id=template.id,
            status=status_flag,
        )

        if dest_res.status_code >= 400:
            error_msg = f"[{dest_url}] {dest_res.text[:2000]}"
            log_job(job.id, "FAILED", payload, http_status=dest_res.status_code, error_message=error_msg)
            _store_failed_payload(job, template, payload, error_msg)
            send_failure_alert(job.id, template.name, dest_url, error_msg)
            return status_flag, dest_res.status_code, error_msg

        log_job(job.id, "SUCCESS", payload, http_status=dest_res.status_code)
        return status_flag, dest_res.status_code, None
    except Exception as exc:
        error_msg = str(exc)
        log_job(job.id, "FAILED", payload, http_status=500, error_message=f"[{dest_url}] {error_msg}")
        _store_failed_payload(job, template, payload, error_msg)
        send_failure_alert(job.id, template.name, dest_url, error_msg)
        return "FAILED", 500, error_msg


def _store_failed_payload(job, template, payload, error_msg):
    from apps.jobs.models import FailedPayload

    try:
        FailedPayload.objects.create(
            job=job,
            template=template,
            payload_json=payload,
            error_message=error_msg,
        )
    except Exception:
        logger.exception("Failed to store failed payload for job %s", job.id)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@shared_task(bind=True, name="apps.jobs.tasks.pull_and_push_job", max_retries=0)
def pull_and_push_job(self, job_id):
    """Core push engine: fetch sources â†’ map â†’ push to all destinations."""
    from apps.core.services.data_transform import build_nested_payload
    from apps.jobs.models import Job
    from apps.realtime.services import broadcast_feed

    job = Job.objects.select_related("template").filter(pk=job_id).first()
    if not job or not job.is_active or not job.template:
        return {"status": "skipped", "reason": "inactive or missing"}

    template = job.template
    logger.info("Starting job %s for template %s", job_id, template.name)

    # 1. Fetch from all sources concurrently.
    aggregated_data = fetch_all_sources(template)

    # 2. Live WebSocket broadcast.
    broadcast_feed(template.id, aggregated_data)

    # 3 & 4. Map & push to destinations.
    destinations = template.destinations or []
    if not destinations and template.client_url:
        destinations = [
            {
                "url": template.client_url,
                "method": "POST",
                "auth_type": template.client_auth_type,
                "credentials": template.client_credentials or {},
                "field_mapping": [],
            }
        ]

    results = []
    for dest in destinations:
        mapping = dest.get("field_mapping", [])
        if mapping:
            final_payload = build_nested_payload(mapping, aggregated_data)
        else:
            final_payload = aggregated_data

        flag, http, err = _push_to_destination(job, template, dest, final_payload)
        results.append({"destination": dest.get("url"), "status": flag, "http": http, "error": err})

    return {"job_id": job_id, "template": template.name, "results": results}


@shared_task(name="apps.jobs.tasks.execute_template_mapping")
def execute_template_mapping(template_id, destination_slug=None):
    """Pull-mode execution: fetch sources and return the transformed payload."""
    from apps.core.services.data_transform import build_nested_payload
    from apps.configs.models import Template

    template = Template.objects.filter(pk=template_id).first()
    if not template:
        return None

    aggregated_data = fetch_all_sources(template)
    _dest, mapping = _resolve_destination(template, destination_slug)

    if mapping:
        return build_nested_payload(mapping, aggregated_data)
    return aggregated_data


@shared_task(name="apps.jobs.tasks.cleanup_failed_payloads")
def cleanup_failed_payloads():
    """Prune FailedPayload records older than the retention window."""
    from datetime import timedelta

    from apps.jobs.models import FailedPayload

    retention_minutes = getattr(settings, "RETRY_QUEUE_RETENTION_MINUTES", 60)
    cutoff = timezone.now() - timedelta(minutes=retention_minutes)
    deleted, _ = FailedPayload.objects.filter(timestamp__lt=cutoff).delete()
    if deleted:
        logger.info("Cleaned up %s expired failed payloads.", deleted)
    return {"deleted": deleted}
