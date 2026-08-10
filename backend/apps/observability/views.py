"""
Observability domain â€” health probes and metrics.

Ports original `health_controller.py` (liveness/readiness) and
`observability_controller.py` (metrics for Zabbix-style HTTP agents).
"""
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.jobs.models import Job, JobLog


@extend_schema(responses=inline_serializer("Liveness", fields={"status": serializers.CharField()}))
@api_view(["GET"])
def liveness_probe(request):
    """Liveness probe â€” the process is up."""
    return Response({"status": "alive"})


@extend_schema(
    responses=inline_serializer(
        "Readiness",
        fields={"status": serializers.CharField(), "database": serializers.CharField(required=False)},
    )
)
@api_view(["GET"])
def readiness_probe(request):
    """Readiness probe â€” DB connectivity check."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ready", "database": "connected"})
    except Exception as exc:  # pragma: no cover - DB down
        return Response({"status": "not_ready", "error": str(exc)}, status=503)


@extend_schema(responses=inline_serializer("Health", fields={"status": serializers.CharField()}))
@api_view(["GET"])
def health(request):
    """Legacy aggregated health endpoint."""
    return Response({"status": "UP"})


@extend_schema(
    responses=inline_serializer(
        "Metrics",
        fields={
            "templates": serializers.JSONField(),
            "jobs": serializers.JSONField(),
            "logs": serializers.JSONField(),
        },
    )
)
@api_view(["GET"])
def metrics(request):
    """Aggregated counters (templates/jobs/logs) for monitoring agents."""
    from apps.configs.models import Template

    return Response(
        {
            "templates": {"total": Template.objects.count()},
            "jobs": {
                "total": Job.objects.count(),
                "active": Job.objects.filter(is_active=True).count(),
            },
            "logs": {
                "total": JobLog.objects.count(),
                "success": JobLog.objects.filter(status="SUCCESS").count(),
                "failed": JobLog.objects.filter(status="FAILED").count(),
            },
        }
    )
