"""Jobs domain viewsets (jobs CRUD + toggle, logs, failed payloads)."""
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.jobs.models import FailedPayload, Job, JobLog
from apps.jobs.serializers import (
    FailedPayloadSerializer,
    JobLogSerializer,
    JobSerializer,
)


class JobViewSet(viewsets.ModelViewSet):
    """CRUD for scheduled jobs, plus start/stop toggling."""

    queryset = Job.objects.select_related("template").all()
    serializer_class = JobSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        """Start or stop a job (is_active flip + Celery beat schedule sync)."""
        job = self.get_object()
        job.is_active = not job.is_active
        job.save(update_fields=["is_active", "updated_at"])
        # Schedule sync is handled via Django signal in apps.jobs.signals.
        return Response(self.get_serializer(job).data)

    @action(detail=False, methods=["post"])
    def bulk_toggle(self, request):
        """Start/stop multiple jobs: POST {action: start|stop, job_ids: [..]}.

        Uses per-object save() (not QuerySet.update) so the post_save signal
        keeps django-celery-beat in sync for every toggled job.
        """
        action = request.data.get("action")
        job_ids = request.data.get("job_ids", [])
        if action not in ("start", "stop") or not job_ids:
            return Response({"error": "action (start|stop) and job_ids required"}, status=400)

        jobs = Job.objects.filter(id__in=job_ids)
        count = 0
        for job in jobs:
            if action == "start" and not job.is_active:
                job.is_active = True
                job.save(update_fields=["is_active", "updated_at"])
                count += 1
            elif action == "stop" and job.is_active:
                job.is_active = False
                job.save(update_fields=["is_active", "updated_at"])
                count += 1
        return Response({"updated": count})


class JobLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only job execution logs, filterable by ?job=<id>."""

    serializer_class = JobLogSerializer

    def get_queryset(self):  # type: ignore[override]
        qs = JobLog.objects.select_related("job").all()
        job_id = self.request.query_params.get("job")  # type: ignore[attr-defined]
        if job_id:
            qs = qs.filter(job_id=job_id)
        return qs


class FailedPayloadViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only failed payloads, filterable by ?job=<id> and ?template=<id>."""

    serializer_class = FailedPayloadSerializer

    def get_queryset(self):  # type: ignore[override]
        qs = FailedPayload.objects.select_related("job", "template").all()
        filters = Q()
        qp = self.request.query_params  # type: ignore[attr-defined]
        if qp.get("job"):
            filters &= Q(job_id=qp["job"])
        if qp.get("template"):
            filters &= Q(template_id=qp["template"])
        return qs.filter(filters)
