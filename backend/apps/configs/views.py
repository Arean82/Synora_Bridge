"""Configs domain viewsets (bridge templates CRUD + clone helper)."""
from rest_framework import viewsets

from apps.configs.models import Template
from apps.configs.serializers import TemplateSerializer


class TemplateViewSet(viewsets.ModelViewSet):
    """CRUD for bridge execution templates."""

    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    lookup_field = "pk"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
