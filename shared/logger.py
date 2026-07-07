"""
Structured logging configuration.

Uses structlog with OpenTelemetry trace correlation.
Every log entry includes: tenant_id, correlation_id, trace_id, span_id.
JSON output in production, colored console in development.

Design Pattern: Facade over structlog + OTel correlation.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from opentelemetry import trace

from shared.settings import get_settings

settings = get_settings()

# ── Context Variables ─────────────────────────────────────────────────────────
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="")
_service_name: ContextVar[str] = ContextVar(
    "service_name", default=settings.service_name
)


def set_correlation_id(value: str) -> None:
    """Set correlation ID for the current async context."""
    _correlation_id.set(value)


def get_correlation_id() -> str:
    """Get correlation ID from the current async context."""
    return _correlation_id.get()


def set_tenant_id(value: str) -> None:
    """Set tenant ID for the current async context."""
    _tenant_id.set(value)


def get_tenant_id() -> str:
    """Get tenant ID from the current async context."""
    return _tenant_id.get()


def set_user_id(value: str) -> None:
    """Set user ID for the current async context."""
    _user_id.set(value)


def get_user_id() -> str:
    """Get user ID from the current async context."""
    return _user_id.get()


def _add_otel_context(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor: inject OpenTelemetry trace context.

    Adds trace_id and span_id to every log entry for correlation
    between logs (Loki) and traces (Tempo/Jaeger).
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
        event_dict["trace_sampled"] = ctx.trace_flags.sampled
    return event_dict


def _add_request_context(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor: inject per-request context variables.

    Adds correlation_id, tenant_id, user_id from contextvars.
    """
    if corr_id := _correlation_id.get():
        event_dict["correlation_id"] = corr_id
    if t_id := _tenant_id.get():
        event_dict["tenant_id"] = t_id
    if u_id := _user_id.get():
        event_dict["user_id"] = u_id
    event_dict["service"] = _service_name.get()
    return event_dict


def _censor_sensitive_fields(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor: redact sensitive fields from logs.

    Prevents accidental logging of PII, secrets, and credentials.
    DPDP 2023 compliance requirement.
    """
    sensitive_keys = {
        "password", "token", "secret", "api_key", "private_key",
        "authorization", "phone", "aadhaar", "pan", "dob", "ssn",
        "credit_card", "bank_account", "cvv", "otp", "pin",
    }
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog for the application.

    JSON format in production, pretty colored output in development.
    All log entries include OTel trace context and request context.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_otel_context,
        _add_request_context,
        _censor_sensitive_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_production:
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level.upper(), logging.INFO)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stdout),
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, settings.log_level.upper(), logging.DEBUG)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(sys.stdout),
            cache_logger_on_first_use=True,
        )

    # Redirect stdlib logging to structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    # Suppress noisy third-party loggers
    for noisy_logger in ["uvicorn.access", "sqlalchemy.engine", "httpx"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a named structured logger.

    Usage:
        logger = get_logger("voice.pipeline")
        logger.info("call_started", call_id=call_id, tenant_id=tenant_id)
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
