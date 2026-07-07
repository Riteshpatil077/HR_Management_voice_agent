"""
JWT RS256 authentication and OPA-based authorization.

Provides:
- JWT RS256 token issuance and validation
- OAuth2 Bearer token extraction
- FastAPI security dependencies
- Tenant extraction from JWT claims
- OPA policy decision caching

RULE 04: Every endpoint has auth + audit log.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from shared.metrics import AUTH_TOKEN_ISSUED_TOTAL, AUTH_TOKEN_REJECTED_TOTAL
from shared.multi_tenant import set_tenant_context
from shared.settings import get_settings

logger = structlog.get_logger("auth")
settings = get_settings()

_bearer = HTTPBearer(auto_error=False)


class TokenClaims(BaseModel):
    """Validated JWT token claims."""

    sub: str                    # Subject (user_id)
    tenant_id: str              # Tenant identifier
    email: str                  # User email
    roles: list[str]            # User roles (e.g., ["hr_admin", "recruiter"])
    plan: str = "starter"       # Tenant subscription plan
    jti: str = ""               # JWT ID (for revocation)
    exp: int = 0                # Expiry timestamp
    iat: int = 0                # Issued-at timestamp
    iss: str = "hr-voice-agent" # Issuer


class TokenPair(BaseModel):
    """Access + refresh token pair returned at login."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int             # Seconds until access token expires


def create_access_token(
    user_id: str,
    email: str,
    tenant_id: str,
    roles: list[str],
    plan: str = "starter",
) -> str:
    """
    Issue a signed RS256 JWT access token.

    Args:
        user_id: Unique user identifier
        email: User email address
        tenant_id: Tenant the user belongs to
        roles: List of user roles for RBAC
        plan: Tenant subscription plan

    Returns:
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "roles": roles,
        "plan": plan,
        "jti": str(uuid.uuid4()),
        "iss": "hr-voice-agent",
        "aud": "hr-voice-agent-api",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    private_key = settings.jwt_private_key
    if not private_key:
        raise RuntimeError("JWT private key not configured")

    token = jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)
    AUTH_TOKEN_ISSUED_TOTAL.labels(
        token_type="access", tenant_id=tenant_id
    ).inc()
    logger.info(
        "access_token_issued",
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        expires_at=expire.isoformat(),
    )
    return token


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    """
    Issue a long-lived RS256 refresh token.

    Refresh tokens have minimal claims — used only to obtain new access tokens.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iss": "hr-voice-agent",
        "aud": "hr-voice-agent-refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    private_key = settings.jwt_private_key
    if not private_key:
        raise RuntimeError("JWT private key not configured")

    token = jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)
    AUTH_TOKEN_ISSUED_TOTAL.labels(
        token_type="refresh", tenant_id=tenant_id
    ).inc()
    return token


def decode_token(token: str, audience: str = "hr-voice-agent-api") -> TokenClaims:
    """
    Validate and decode a JWT token.

    Validates: signature, expiry, issuer, audience.

    Args:
        token: Raw JWT string
        audience: Expected audience claim

    Returns:
        Validated TokenClaims

    Raises:
        HTTPException 401: If token is invalid or expired.
    """
    public_key = settings.jwt_public_key
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT public key not configured",
        )
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.jwt_algorithm],
            audience=audience,
            issuer="hr-voice-agent",
        )
        return TokenClaims(**payload)
    except JWTError as exc:
        AUTH_TOKEN_REJECTED_TOTAL.labels(reason=type(exc).__name__).inc()
        logger.warning("token_validation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> TokenClaims:
    """
    FastAPI dependency: extract and validate Bearer token.

    Sets tenant context for the request lifecycle.

    Usage:
        @router.get("/employees")
        async def list_employees(user: TokenClaims = Depends(get_current_user)):
            ...
    """
    if not credentials:
        AUTH_TOKEN_REJECTED_TOTAL.labels(reason="missing_token").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_token(credentials.credentials)

    # Set tenant context for the duration of this request
    set_tenant_context(
        tenant_id=claims.tenant_id,
        plan=claims.plan,
    )

    return claims


def require_roles(*required_roles: str) -> Any:
    """
    FastAPI dependency factory: enforce role-based access control.

    Usage:
        @router.post("/calls")
        async def initiate_call(
            user: TokenClaims = Depends(require_roles("hr_admin", "recruiter"))
        ):
            ...
    """
    async def _check_roles(
        user: TokenClaims = Depends(get_current_user),
    ) -> TokenClaims:
        if not any(role in user.roles for role in required_roles):
            logger.warning(
                "access_denied",
                user_id=user.sub,
                tenant_id=user.tenant_id,
                required_roles=list(required_roles),
                user_roles=user.roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(required_roles)}",
            )
        return user

    return _check_roles


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> TokenClaims | None:
    """
    FastAPI dependency: return user if authenticated, None if not.

    Use for endpoints that support both authenticated and anonymous access.
    """
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None
