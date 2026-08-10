"""Core domain viewsets (app settings, audit log)."""
from rest_framework import viewsets

from apps.core.models import AppSetting, AuditLog
from apps.core.serializers import AppSettingSerializer, AuditLogSerializer


class AppSettingViewSet(viewsets.ModelViewSet):
    """Key/value runtime settings (UI theme, layout, date format).

    Lookup by primary key (ids are stable); filter the list with ?key=<name>
    (keys may contain dots, which the default router regex would reject).
    """

    queryset = AppSetting.objects.all()
    serializer_class = AppSettingSerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):  # type: ignore[override]
        qs = AppSetting.objects.all()
        key = self.request.query_params.get("key")  # type: ignore[attr-defined]
        if key:
            qs = qs.filter(key=key)
        return qs


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail, filterable by mode/template/status."""

    serializer_class = AuditLogSerializer

    def get_queryset(self):  # type: ignore[override]
        qs = AuditLog.objects.select_related("template").all()
        qp = self.request.query_params  # type: ignore[attr-defined]
        if qp.get("mode"):
            qs = qs.filter(mode=qp["mode"].upper())
        if qp.get("template"):
            qs = qs.filter(template_id=qp["template"])
        if qp.get("status"):
            qs = qs.filter(status=qp["status"].upper())
        return qs
