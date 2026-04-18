from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def configure_tracing(env: str = "dev", service_name: str = "migration-agent") -> None:
    """Configure OpenTelemetry tracing. In dev, exports to console (no-op if quiet)."""
    resource = Resource.create({"service.name": service_name, "deployment.environment": env})
    provider = TracerProvider(resource=resource)

    if env == "dev":
        # Console exporter so we can see spans locally without a real collector
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # In prod/staging, Cloud Trace exporter is configured via the GCP OTel library.
        # Import only when available so local dev doesn't require GCP credentials.
        try:
            from opentelemetry.exporter.cloud_trace import (
                CloudTraceSpanExporter,  # type: ignore[import-untyped]
            )

            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        except ImportError:
            pass

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
