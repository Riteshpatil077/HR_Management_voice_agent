"""
Multi-tenant context management.

Provides:
- Async context variables for tenant isolation
- PostgreSQL schema routing per tenant
- Redis cache namespace builder
- S3 path prefix builder
- Tenant validation and resolution

RULE 11: Every tenant has isolated DB schema + cache prefix +
queue + storage path + encryption key.

Design Pattern: Context Object Pattern
"""
from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger("multi_tenant")

# ── Context Variables ─────────────────────────────────────────────────────────
_current_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="")
_current_tenant_schema: ContextVar[str] = ContextVar("tenant_schema", default="public")
_current_tenant_plan: ContextVar[str] = ContextVar("tenant_plan", default="free")

TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{2,61}[a-z0-9]$")
RESERVED_SCHEMAS = frozenset(
    {"public", "pg_catalog", "information_schema", "pg_toast", "shared", "admin"}
)


@dataclass(frozen=True)
class TenantContext:
    """Immutable snapshot of tenant context for the current request."""

    tenant_id: str
    schema_name: str
    plan: str
    cache_prefix: str
    s3_prefix: str
    queue_prefix: str


class TenantNotFoundError(Exception):
    """Raised when a tenant ID is not recognized."""


class InvalidTenantIDError(ValueError):
    """Raised when a tenant ID fails validation."""


def validate_tenant_id(tenant_id: str) -> None:
    """
    Validate tenant ID format.

    Must be 4-63 characters, lowercase alphanumeric + hyphens.
    Cannot start or end with a hyphen.
    Cannot be a reserved schema name.

    Raises:
        InvalidTenantIDError: If validation fails.
    """
    if not tenant_id:
        raise InvalidTenantIDError("Tenant ID cannot be empty")
    if not TENANT_ID_PATTERN.match(tenant_id):
        raise InvalidTenantIDError(
            f"Invalid tenant ID '{tenant_id}'. "
            "Must be 4-63 lowercase alphanumeric characters or hyphens, "
            "not starting or ending with a hyphen."
        )
    schema = tenant_id_to_schema(tenant_id)
    if schema in RESERVED_SCHEMAS:
        raise InvalidTenantIDError(
            f"Tenant ID '{tenant_id}' maps to reserved schema '{schema}'"
        )


def tenant_id_to_schema(tenant_id: str) -> str:
    """
    Convert tenant ID to PostgreSQL schema name.

    Format: tenant_{tenant_id_with_underscores}
    Example: "acme-corp" → "tenant_acme_corp"
    """
    sanitized = tenant_id.replace("-", "_").lower()
    return f"tenant_{sanitized}"


def set_tenant_context(
    tenant_id: str,
    plan: str = "starter",
) -> tuple[Token[str], Token[str], Token[str]]:
    """
    Set tenant context for the current async task.

    Returns tokens for resetting context after request completes.

    Args:
        tenant_id: The tenant identifier
        plan: Subscription plan tier

    Returns:
        Tuple of reset tokens for all context variables
    """
    validate_tenant_id(tenant_id)
    schema = tenant_id_to_schema(tenant_id)

    t1 = _current_tenant_id.set(tenant_id)
    t2 = _current_tenant_schema.set(schema)
    t3 = _current_tenant_plan.set(plan)
    return t1, t2, t3


def reset_tenant_context(
    tokens: tuple[Token[str], Token[str], Token[str]],
) -> None:
    """Reset all tenant context variables using saved tokens."""
    _current_tenant_id.reset(tokens[0])
    _current_tenant_schema.reset(tokens[1])
    _current_tenant_plan.reset(tokens[2])


def get_current_tenant_id() -> str:
    """
    Get the current tenant ID from context.

    Raises:
        TenantNotFoundError: If no tenant is set in the current context.
    """
    tenant_id = _current_tenant_id.get()
    if not tenant_id:
        raise TenantNotFoundError(
            "No tenant ID set in current context. "
            "Ensure TenantMiddleware is configured and request has X-Tenant-ID header."
        )
    return tenant_id


def get_current_schema() -> str:
    """Get the current tenant's PostgreSQL schema name."""
    return _current_tenant_schema.get()


def get_current_plan() -> str:
    """Get the current tenant's subscription plan."""
    return _current_tenant_plan.get()


def get_tenant_context() -> TenantContext:
    """
    Get a complete snapshot of the current tenant context.

    Returns a frozen dataclass with all tenant-specific namespace values.
    """
    tenant_id = get_current_tenant_id()
    schema = get_current_schema()
    plan = get_current_plan()
    return TenantContext(
        tenant_id=tenant_id,
        schema_name=schema,
        plan=plan,
        cache_prefix=build_cache_prefix(tenant_id),
        s3_prefix=build_s3_prefix(tenant_id),
        queue_prefix=build_queue_prefix(tenant_id),
    )


def build_cache_prefix(tenant_id: str) -> str:
    """
    Build tenant-specific Redis cache key prefix.

    Format: t:{tenant_id}:
    Example: t:acme-corp:voice:sessions
    """
    return f"t:{tenant_id}:"


def build_cache_key(tenant_id: str, namespace: str, key: str) -> str:
    """
    Build a fully-qualified, tenant-namespaced cache key.

    Example: build_cache_key("acme-corp", "voice", "session:abc123")
             → "t:acme-corp:voice:session:abc123"
    """
    prefix = build_cache_prefix(tenant_id)
    return f"{prefix}{namespace}:{key}"


def build_s3_prefix(tenant_id: str) -> str:
    """
    Build tenant-specific S3 object key prefix.

    Format: tenants/{tenant_id}/
    Example: tenants/acme-corp/recordings/2024/01/audio.wav
    """
    return f"tenants/{tenant_id}/"


def build_queue_prefix(tenant_id: str) -> str:
    """
    Build tenant-specific RabbitMQ routing key prefix.

    Format: tenant.{tenant_id}.
    Example: tenant.acme-corp.voice.generate
    """
    return f"tenant.{tenant_id}."


def require_tenant() -> str:
    """
    Dependency for FastAPI routes that require a valid tenant.

    Use with FastAPI Depends:
        @router.get("/employees")
        async def list_employees(tenant_id: str = Depends(require_tenant)):
            ...
    """
    return get_current_tenant_id()
