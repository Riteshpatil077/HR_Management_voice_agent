"""
Idempotency key management.

RULE 20: Idempotency keys on all mutating API endpoints.

All POST/PUT/PATCH/DELETE endpoints must accept an Idempotency-Key header.
If the same key is used twice, the original response is returned without
re-executing the operation.

Implementation:
- Key stored in Redis with 24h TTL
- Value is the serialized response (status code + body)
- FastAPI dependency extracts and validates the key
- Decorator stores response after successful execution

Design Pattern: Idempotent Consumer
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

import structlog
from fastapi import Header, HTTPException, Request, Response, status

from shared.cache import CacheClient, get_redis
from shared.settings import get_settings

logger = structlog.get_logger("idempotency")
settings = get_settings()

IDEMPOTENCY_KEY_TTL = 86400  # 24 hours
IDEMPOTENCY_NAMESPACE = "idempotency"


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is currently being processed."""


class IdempotencyStore:
    """
    Redis-backed idempotency key store.

    Stores: {key → {status_code, headers, body, tenant_id, created_at}}
    """

    def __init__(self, tenant_id: str) -> None:
        self._cache = CacheClient(IDEMPOTENCY_NAMESPACE, tenant_id)
        self._tenant_id = tenant_id

    @staticmethod
    def _hash_key(idempotency_key: str, path: str, tenant_id: str) -> str:
        """
        Create a deterministic hash for the cache key.

        Combines idempotency key + endpoint path + tenant to prevent
        key collisions across endpoints and tenants.
        """
        raw = f"{tenant_id}:{path}:{idempotency_key}"
        return hashlib.sha256(raw.encode()).hexdigest()[:48]

    async def get_stored_response(
        self, idempotency_key: str, path: str
    ) -> dict[str, Any] | None:
        """
        Retrieve a previously stored response for this key.

        Returns:
            Stored response dict or None if not found.
        """
        cache_key = self._hash_key(idempotency_key, path, self._tenant_id)
        return await self._cache.get(cache_key)

    async def store_response(
        self,
        idempotency_key: str,
        path: str,
        status_code: int,
        headers: dict[str, str],
        body: Any,
    ) -> None:
        """
        Store the response for a completed request.

        Args:
            idempotency_key: Client-provided key
            path: Request path (included in cache key for safety)
            status_code: HTTP response status code
            headers: Response headers to replay
            body: Serializable response body
        """
        cache_key = self._hash_key(idempotency_key, path, self._tenant_id)
        record = {
            "status_code": status_code,
            "headers": headers,
            "body": body,
            "idempotency_key": idempotency_key,
            "path": path,
            "tenant_id": self._tenant_id,
        }
        await self._cache.set(cache_key, record, ttl=IDEMPOTENCY_KEY_TTL)
        logger.info(
            "idempotency_response_stored",
            key=idempotency_key,
            path=path,
            status_code=status_code,
            tenant_id=self._tenant_id,
        )

    async def mark_in_flight(self, idempotency_key: str, path: str) -> bool:
        """
        Mark a request as in-flight (being processed).

        Returns True if successfully marked (i.e., key was not already in-flight).
        Uses SET NX for atomicity.
        """
        cache_key = self._hash_key(idempotency_key, path, self._tenant_id) + ":lock"
        redis = await get_redis()
        result = await redis.set(
            cache_key,
            "1",
            nx=True,
            ex=300,  # 5 minute lock timeout
        )
        return bool(result)

    async def clear_in_flight(self, idempotency_key: str, path: str) -> None:
        """Clear the in-flight marker after request completes."""
        cache_key = self._hash_key(idempotency_key, path, self._tenant_id) + ":lock"
        redis = await get_redis()
        await redis.delete(cache_key)


async def get_idempotency_key(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> str | None:
    """
    FastAPI dependency: extract and validate Idempotency-Key header.

    Optional — returns None if header not present.
    Validates key format (non-empty, max 255 chars).

    Usage:
        @router.post("/calls")
        async def initiate_call(
            idem_key: str | None = Depends(get_idempotency_key),
        ):
            ...
    """
    if idempotency_key is None:
        return None
    if not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header must not be empty",
        )
    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header must not exceed 255 characters",
        )
    return idempotency_key.strip()


def require_idempotency_key(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> str:
    """
    FastAPI dependency: require Idempotency-Key header.

    Use on critical mutating endpoints (payment, call initiation, etc.)

    Raises:
        HTTPException 400: If header is missing or invalid.
    """
    if not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required and must not be empty",
        )
    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header must not exceed 255 characters",
        )
    return idempotency_key.strip()
