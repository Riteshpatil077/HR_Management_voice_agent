"""
RFC 7807 Problem Details for HTTP APIs.

All error responses in the platform use this format.
RULE 19: RFC 7807 Problem Details on all error responses.

Spec: https://www.rfc-editor.org/rfc/rfc7807
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """
    RFC 7807 Problem Details response model.

    Content-Type: application/problem+json
    """

    type: str = Field(
        description="URI reference identifying the problem type",
        examples=["https://hrvoice.io/errors/validation-error"],
    )
    title: str = Field(
        description="Short, human-readable summary of the problem",
        examples=["Validation Error"],
    )
    status: int = Field(
        description="HTTP status code",
        examples=[400],
    )
    detail: str = Field(
        description="Human-readable explanation specific to this occurrence",
        examples=["The 'phone' field must be a valid E.164 phone number"],
    )
    instance: str = Field(
        default="",
        description="URI reference identifying this specific occurrence",
        examples=["/v1/calls/abc123"],
    )
    correlation_id: str = Field(
        default="",
        description="Request correlation ID for support tracing",
    )
    errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed field-level validation errors",
    )

    model_config = {"extra": "allow"}  # Allow extension members


def problem_response(
    type_: str,
    title: str,
    status: int,
    detail: str,
    instance: str = "",
    correlation_id: str = "",
    errors: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> JSONResponse:
    """
    Build an RFC 7807 Problem Details JSON response.

    Args:
        type_: Problem type URI
        title: Short problem title
        status: HTTP status code
        detail: Detailed explanation
        instance: URI of affected resource
        correlation_id: Request correlation ID
        errors: Field-level validation errors
        **extra: Additional extension members

    Returns:
        JSONResponse with Content-Type: application/problem+json
    """
    body = ProblemDetail(
        type=type_,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        correlation_id=correlation_id,
        errors=errors or [],
        **extra,
    )
    return JSONResponse(
        content=body.model_dump(exclude_none=False),
        status_code=status,
        media_type="application/problem+json",
        headers={
            "Content-Type": "application/problem+json",
            "X-Correlation-ID": correlation_id,
        },
    )


# ── Pre-built Error Factories ──────────────────────────────────────────────────

def not_found(resource: str, resource_id: str, instance: str = "") -> JSONResponse:
    """Return a 404 Not Found Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/not-found",
        title="Resource Not Found",
        status=404,
        detail=f"{resource} with ID '{resource_id}' was not found.",
        instance=instance,
    )


def validation_error(
    detail: str,
    errors: list[dict[str, Any]] | None = None,
    instance: str = "",
) -> JSONResponse:
    """Return a 422 Validation Error Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/validation-error",
        title="Validation Error",
        status=422,
        detail=detail,
        instance=instance,
        errors=errors or [],
    )


def unauthorized(detail: str = "Authentication required") -> JSONResponse:
    """Return a 401 Unauthorized Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/unauthorized",
        title="Unauthorized",
        status=401,
        detail=detail,
    )


def forbidden(detail: str = "Insufficient permissions") -> JSONResponse:
    """Return a 403 Forbidden Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/forbidden",
        title="Forbidden",
        status=403,
        detail=detail,
    )


def rate_limited(retry_after: int = 60) -> JSONResponse:
    """Return a 429 Too Many Requests Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/rate-limited",
        title="Too Many Requests",
        status=429,
        detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
        retry_after=retry_after,
    )


def conflict(resource: str, reason: str, instance: str = "") -> JSONResponse:
    """Return a 409 Conflict Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/conflict",
        title="Conflict",
        status=409,
        detail=f"{resource} conflict: {reason}",
        instance=instance,
    )


def internal_error(
    correlation_id: str = "",
    detail: str = "An unexpected internal error occurred.",
) -> JSONResponse:
    """Return a 500 Internal Server Error Problem response."""
    return problem_response(
        type_="https://hrvoice.io/errors/internal-error",
        title="Internal Server Error",
        status=500,
        detail=detail,
        correlation_id=correlation_id,
    )


def service_unavailable(
    provider: str, recovery_in: float | None = None
) -> JSONResponse:
    """Return a 503 Service Unavailable Problem response."""
    detail = f"External service '{provider}' is currently unavailable."
    if recovery_in:
        detail += f" Estimated recovery in {recovery_in:.0f} seconds."
    return problem_response(
        type_="https://hrvoice.io/errors/service-unavailable",
        title="Service Unavailable",
        status=503,
        detail=detail,
    )


# ── Global Exception Handlers ──────────────────────────────────────────────────

async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Global handler for unhandled exceptions.

    Register with FastAPI:
        app.add_exception_handler(Exception, unhandled_exception_handler)
    """
    import structlog
    correlation_id = request.headers.get("X-Correlation-ID", "")
    log = structlog.get_logger("exception_handler")
    log.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
        correlation_id=correlation_id,
    )
    return internal_error(correlation_id=correlation_id)
