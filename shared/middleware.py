"""
FastAPI middleware stack.

Applied in order (outermost to innermost):
1. CorrelationIDMiddleware — inject X-Correlation-ID into every request/response
2. TenantMiddleware — extract X-Tenant-ID, set context, validate
3. SecurityHeadersMiddleware — HSTS, CSP, X-Frame-Options, etc.
4. RequestLoggingMiddleware — structured request/response logging
5. MetricsMiddleware — Prometheus HTTP metrics

RULE 04: Every endpoint must go through auth + request logging + audit.
RULE 08: No synchronous blocking inside async routes.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from shared.logger import set_correlation_id, set_tenant_id
from shared.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_FLIGHT,
    HTTP_REQUESTS_TOTAL,
)
from shared.multi_tenant import (
    InvalidTenantIDError,
    set_tenant_context,
    reset_tenant_context,
)
from shared.problem_details import ProblemDetail
from shared.settings import get_settings

logger = structlog.get_logger("middleware")
settings = get_settings()

# Endpoints excluded from tenant requirement
_TENANT_EXCLUDED_PATHS = frozenset(
    {
        "/health",
        "/readiness",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/auth/register",
        "/v1/webhooks",
    }
)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Inject X-Correlation-ID header into every request and response.

    If the request already has X-Correlation-ID, it is preserved.
    Otherwise a new UUID4 is generated.
    Injects the ID into the log context for structured logging.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = (
            request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        )
        set_correlation_id(correlation_id)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extract and validate X-Tenant-ID header.

    Sets tenant context for the duration of the request.
    Returns 400 if header is missing on tenant-required endpoints.
    Returns 400 if tenant ID format is invalid.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip tenant enforcement for public endpoints
        if any(path.startswith(excluded) for excluded in _TENANT_EXCLUDED_PATHS):
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if not tenant_id:
            return Response(
                content=ProblemDetail(
                    type="https://hrvoice.io/errors/missing-tenant",
                    title="Missing Tenant ID",
                    status=400,
                    detail="X-Tenant-ID header is required for this endpoint.",
                    instance=str(request.url),
                ).model_dump_json(),
                status_code=400,
                media_type="application/problem+json",
            )

        try:
            tokens = set_tenant_context(tenant_id=tenant_id)
        except InvalidTenantIDError as exc:
            return Response(
                content=ProblemDetail(
                    type="https://hrvoice.io/errors/invalid-tenant",
                    title="Invalid Tenant ID",
                    status=400,
                    detail=str(exc),
                    instance=str(request.url),
                ).model_dump_json(),
                status_code=400,
                media_type="application/problem+json",
            )

        set_tenant_id(tenant_id)

        try:
            response = await call_next(request)
        finally:
            reset_tenant_context(tokens)

        response.headers["X-Tenant-ID"] = tenant_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security response headers to all responses.

    Headers applied:
    - Strict-Transport-Security (HSTS)
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection
    - Content-Security-Policy
    - Referrer-Policy
    - Permissions-Policy
    - Cache-Control for API responses
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'none';"
        )
        # Prevent caching of API responses
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, private"
            )
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log every request and response with structured metadata.

    Logs: method, path, status_code, latency_ms, tenant_id, correlation_id.
    Excludes health check endpoints to reduce log noise.
    """

    _skip_paths = frozenset({"/health", "/readiness", "/metrics"})

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self._skip_paths:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        status_code = response.status_code
        log_fn = logger.warning if status_code >= 400 else logger.info

        log_fn(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            latency_ms=latency_ms,
            user_agent=request.headers.get("User-Agent", ""),
            content_length=response.headers.get("Content-Length", ""),
            query_string=str(request.url.query),
        )
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Record Prometheus HTTP metrics for every request.

    Tracks: total requests, latency histogram, in-flight gauge.
    Groups paths to avoid high cardinality (e.g., /v1/calls/uuid → /v1/calls/{id}).
    """

    def __init__(self, app: ASGIApp, service_name: str) -> None:
        super().__init__(app)
        self._service = service_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = self._normalize_path(request.url.path)
        method = request.method

        HTTP_REQUESTS_IN_FLIGHT.labels(service=self._service).inc()
        start = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            latency = time.perf_counter() - start
            HTTP_REQUESTS_IN_FLIGHT.labels(service=self._service).dec()
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
                service=self._service,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=path, service=self._service
            ).observe(latency)

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        """
        Normalize path to reduce Prometheus label cardinality.

        Replaces UUIDs and numeric IDs with placeholders.
        Example: /v1/calls/550e8400-e29b-41d4-a716-446655440000 → /v1/calls/{id}
        """
        import re
        # Replace UUID segments
        path = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{id}",
            path,
        )
        # Replace numeric IDs
        path = re.sub(r"/\d+", "/{id}", path)
        return path
