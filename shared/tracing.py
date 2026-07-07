"""
OpenTelemetry tracing configuration.

Sets up unified observability: traces + metrics + logs.
Uses OTLP gRPC exporter to send to the OTel Collector.
Auto-instruments FastAPI, SQLAlchemy, Redis, and HTTPX.

Design Pattern: Singleton setup at application startup.
"""
from __future__ import annotations

from opentelemetry import metrics as otel_metrics
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

import structlog

from shared.settings import get_settings

logger = structlog.get_logger("tracing")
settings = get_settings()

_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None


def setup_tracing(service_name: str | None = None) -> None:
    """
    Initialize OpenTelemetry tracing and metrics.

    Call once at application startup before serving requests.

    Args:
        service_name: Override the default service name from settings.
    """
    global _tracer_provider, _meter_provider

    svc_name = service_name or settings.otel_service_name
    resource = Resource.create(
        {
            "service.name": svc_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.app_env,
            "service.namespace": "hr-voice-agent",
        }
    )

    # ── Tracer Provider ───────────────────────────────────────────────────
    sampler = ParentBasedTraceIdRatio(
        root=settings.otel_traces_sampler_arg,
    )
    _tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    otlp_span_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=not settings.is_production,
    )
    _tracer_provider.add_span_processor(
        BatchSpanProcessor(
            otlp_span_exporter,
            max_queue_size=2048,
            schedule_delay_millis=5000,
            max_export_batch_size=512,
            export_timeout_millis=30000,
        )
    )
    trace.set_tracer_provider(_tracer_provider)

    # ── Meter Provider ────────────────────────────────────────────────────
    otlp_metric_exporter = OTLPMetricExporter(
        endpoint=settings.otel_exporter_endpoint,
        insecure=not settings.is_production,
    )
    metric_reader = PeriodicExportingMetricReader(
        exporter=otlp_metric_exporter,
        export_interval_millis=15000,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    otel_metrics.set_meter_provider(_meter_provider)

    # ── Auto-instrumentation ──────────────────────────────────────────────
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

    logger.info(
        "otel_initialized",
        service=svc_name,
        endpoint=settings.otel_exporter_endpoint,
        sample_rate=settings.otel_traces_sampler_arg,
    )


def instrument_fastapi(app: "FastAPI") -> None:  # type: ignore[name-defined]  # noqa: F821
    """
    Instrument a FastAPI application with OpenTelemetry.

    Call after setup_tracing() and after app creation.
    """
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,readiness,metrics",
        tracer_provider=_tracer_provider,
        meter_provider=_meter_provider,
    )
    logger.info("fastapi_instrumented")


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a named tracer for manual span creation.

    Usage:
        tracer = get_tracer("voice.pipeline")
        with tracer.start_as_current_span("stt_transcribe") as span:
            span.set_attribute("audio.duration_seconds", 5.2)
            result = await transcribe(audio)
    """
    return trace.get_tracer(name)


def get_meter(name: str) -> otel_metrics.Meter:
    """Get a named meter for manual metric recording."""
    return otel_metrics.get_meter(name)


async def shutdown_tracing() -> None:
    """Flush and shutdown telemetry providers on graceful shutdown."""
    if _tracer_provider:
        _tracer_provider.shutdown()
    if _meter_provider:
        _meter_provider.shutdown()
    logger.info("otel_shutdown")
