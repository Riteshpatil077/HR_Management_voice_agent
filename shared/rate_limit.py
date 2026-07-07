"""
Token bucket rate limiter backed by Redis.

RULE 04: Every endpoint has rate limiting.

Implements per-tenant and per-endpoint token bucket algorithm in Redis.
Uses atomic Lua script for race-condition-free token consumption.

Limits configured per endpoint category:
- Default: 100 req/min
- Voice: 20 req/min
- Auth: 10 req/min
- Webhook: 500 req/min
"""
from __future__ import annotations

import time
from enum import Enum
from typing import NamedTuple

import structlog
from fastapi import HTTPException, Request, status

from shared.cache import get_redis
from shared.metrics import HTTP_REQUESTS_TOTAL
from shared.problem_details import rate_limited
from shared.settings import get_settings

logger = structlog.get_logger("rate_limit")
settings = get_settings()


class RateLimitCategory(str, Enum):
    """Rate limit categories with different thresholds."""

    DEFAULT = "default"
    VOICE = "voice"
    AUTH = "auth"
    WEBHOOK = "webhook"
    LLM = "llm"


class RateLimitConfig(NamedTuple):
    """Rate limit configuration: requests per window."""

    requests: int
    window_seconds: int


# ── Rate Limit Configurations ─────────────────────────────────────────────────
RATE_LIMIT_CONFIGS: dict[RateLimitCategory, RateLimitConfig] = {
    RateLimitCategory.DEFAULT: RateLimitConfig(requests=100, window_seconds=60),
    RateLimitCategory.VOICE: RateLimitConfig(requests=20, window_seconds=60),
    RateLimitCategory.AUTH: RateLimitConfig(requests=10, window_seconds=60),
    RateLimitCategory.WEBHOOK: RateLimitConfig(requests=500, window_seconds=60),
    RateLimitCategory.LLM: RateLimitConfig(requests=50, window_seconds=60),
}

# Lua script for atomic token bucket check-and-consume
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local window = tonumber(ARGV[3])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end

if count > capacity then
    local ttl = redis.call('TTL', key)
    return {0, count, ttl}
end

return {1, count, -1}
"""


class RateLimitResult(NamedTuple):
    """Result of a rate limit check."""

    allowed: bool
    current_count: int
    retry_after: int      # Seconds until window resets (when denied)
    limit: int
    remaining: int


class RateLimiter:
    """
    Token bucket rate limiter using Redis atomic operations.

    Keys are namespaced per tenant + endpoint + category.
    """

    async def check(
        self,
        identifier: str,            # e.g., "tenant:acme-corp" or "ip:1.2.3.4"
        category: RateLimitCategory = RateLimitCategory.DEFAULT,
        endpoint: str = "",
    ) -> RateLimitResult:
        """
        Check and consume a token from the rate limit bucket.

        Args:
            identifier: Unique identifier (tenant_id, IP, user_id)
            category: Rate limit category for config lookup
            endpoint: Optional endpoint path for granular limiting

        Returns:
            RateLimitResult with allowed flag and metadata.
        """
        config = RATE_LIMIT_CONFIGS[category]
        now = int(time.time())
        window_start = now - (now % config.window_seconds)
        cache_key = f"ratelimit:{identifier}:{category.value}:{endpoint}:{window_start}"

        try:
            redis = await get_redis()
            result = await redis.eval(
                _TOKEN_BUCKET_LUA,
                1,
                cache_key,
                config.requests,
                now,
                config.window_seconds,
            )
            allowed = bool(result[0])
            current_count = int(result[1])
            retry_after = int(result[2]) if result[2] != -1 else 0
            remaining = max(0, config.requests - current_count)

            return RateLimitResult(
                allowed=allowed,
                current_count=current_count,
                retry_after=retry_after,
                limit=config.requests,
                remaining=remaining,
            )

        except Exception as exc:
            # On Redis error, fail open (allow request) to prevent service disruption
            logger.warning(
                "rate_limit_check_failed",
                identifier=identifier,
                category=category.value,
                error=str(exc),
            )
            return RateLimitResult(
                allowed=True,
                current_count=0,
                retry_after=0,
                limit=config.requests,
                remaining=config.requests,
            )


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Return the singleton rate limiter."""
    return _limiter


async def enforce_rate_limit(
    request: Request,
    category: RateLimitCategory = RateLimitCategory.DEFAULT,
) -> RateLimitResult:
    """
    FastAPI dependency: enforce rate limiting.

    Extracts tenant_id from request headers for per-tenant limiting.
    Falls back to client IP if no tenant header.

    Raises:
        HTTPException 429: When rate limit is exceeded.

    Usage:
        @router.post("/calls")
        async def initiate_call(
            _: RateLimitResult = Depends(
                lambda req: enforce_rate_limit(req, RateLimitCategory.VOICE)
            )
        ):
            ...
    """
    tenant_id = request.headers.get("X-Tenant-ID", "")
    identifier = f"tenant:{tenant_id}" if tenant_id else f"ip:{request.client.host}"  # type: ignore[union-attr]

    result = await _limiter.check(
        identifier=identifier,
        category=category,
        endpoint=request.url.path,
    )

    if not result.allowed:
        logger.warning(
            "rate_limit_exceeded",
            identifier=identifier,
            category=category.value,
            path=request.url.path,
            count=result.current_count,
            limit=result.limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {result.retry_after} seconds.",
            headers={
                "Retry-After": str(result.retry_after),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + result.retry_after),
            },
        )

    return result
