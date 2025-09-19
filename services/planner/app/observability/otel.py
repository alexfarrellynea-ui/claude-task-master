"""OpenTelemetry helpers for the planner service."""
from __future__ import annotations

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ..config import get_settings


def configure_telemetry() -> None:
    """Configure tracing and metrics exporters."""
    settings = get_settings()
    resource = Resource(attributes={SERVICE_NAME: settings.observability.otel_service_name})

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    if settings.observability.otel_exporter_otlp_endpoint:
        span_exporter = OTLPSpanExporter(endpoint=settings.observability.otel_exporter_otlp_endpoint)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

        metric_exporter = OTLPMetricExporter(endpoint=settings.observability.otel_exporter_otlp_endpoint)
        reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)


__all__ = ["configure_telemetry"]
