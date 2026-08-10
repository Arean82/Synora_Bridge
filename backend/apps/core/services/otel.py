"""
OpenTelemetry wiring (scale item #7) — config-driven instrumentation.

Enabled via config.ini [OPENTELEMETRY] enabled=true. Instruments the
Django request cycle, DB queries, outbound requests, and Celery tasks;
exports traces via OTLP to the configured endpoint.

The required packages (opentelemetry-distro, opentelemetry-instrumentation-*,
opentelemetry-exporter-otlp) are optional dependencies — import is guarded so
the app runs without them when tracing is disabled.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def setup_otel():
    """Start OpenTelemetry instrumentation when [OPENTELEMETRY] enabled=true.

    Safe to call multiple times; returns early when disabled.
    """
    if not getattr(settings, "OTEL_ENABLED", False):
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        instrument = settings.OTEL_INSTRUMENT
        if instrument.get("django"):
            from opentelemetry.instrumentation.django import DjangoInstrumentor

            DjangoInstrumentor().instrument()
        if instrument.get("requests"):
            from opentelemetry.instrumentation.requests import RequestsInstrumentor

            RequestsInstrumentor().instrument()
        if instrument.get("celery"):
            from opentelemetry.instrumentation.celery import CeleryInstrumentor  # type: ignore[import-not-found]

            CeleryInstrumentor().instrument()
        if instrument.get("db"):
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            SQLAlchemyInstrumentor().instrument()
        if instrument.get("http"):
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import-not-found]

            HTTPXClientInstrumentor().instrument()

        logger.info("OpenTelemetry enabled (service=%s, endpoint=%s)", settings.OTEL_SERVICE_NAME, settings.OTEL_EXPORTER_OTLP_ENDPOINT)
    except ImportError:
        logger.warning(
            "OpenTelemetry is enabled in config.ini but the opentelemetry "
            "packages are not installed. Install: pip install opentelemetry-distro "
            "opentelemetry-instrumentation-django opentelemetry-instrumentation-requests "
            "opentelemetry-instrumentation-celery opentelemetry-instrumentation-sqlalchemy "
            "opentelemetry-instrumentation-httpx opentelemetry-exporter-otlp"
        )
    except Exception:
        logger.exception("Failed to initialize OpenTelemetry instrumentation")
