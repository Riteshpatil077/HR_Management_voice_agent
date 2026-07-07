"""
Redis Cluster async client.

Provides:
- Tenant-namespaced key builder (RULE 11)
- Async get/set/delete with serialization
- Distributed lock (Redlock)
- Rate limiting token bucket
- Session management
- Semantic cache for LLM responses

Uses redis-py in cluster mode with hiredis parser for performance.
All keys are namespaced per tenant to enforce isolation.

Design Pattern: Facade + Repository
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, TypeVar

import structlog
from redis.asyncio.cluster import RedisCluster
from redis.exceptions import RedisClusterException, RedisError

from shared.metrics import (
    CACHE_ERRORS_TOTAL,
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    CACHE_OPERATION_DURATION_SECONDS,
)
from shared.multi_tenant import build_cache_key
from shared.settings import get_settings

logger = structlog.get_logger("cache")
settings = get_settings()
T = TypeVar("T")

_cluster: RedisCluster | None = None
_cluster_lock = asyncio.Lock()


async def get_redis() -> RedisCluster:
    """
    Get or create the Redis Cluster client (singleton).

    Uses double-checked locking for thread safety.
    """
    global _cluster
    if _cluster is not None:
        return _cluster
    async with _cluster_lock:
        if _cluster is not None:
            return _cluster
        startup_nodes = [
            {"host": node["host"], "port": node["port"]}
            for node in settings.redis_node_list
        ]
        _cluster = RedisCluster(
            startup_nodes=startup_nodes,
            password=settings.redis_password or None,
            ssl=settings.redis_ssl,
            decode_responses=False,
            skip_full_coverage_check=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            max_connections=100,
        )
        logger.info("redis_cluster_connected", nodes=len(startup_nodes))
    return _cluster


async def close_redis() -> None:
    """Close the Redis Cluster connection on shutdown."""
    global _cluster
    if _cluster:
        await _cluster.aclose()
        _cluster = None
        logger.info("redis_cluster_closed")


class CacheClient:
    """
    High-level cache client with tenant isolation.

    All operations are automatically namespaced by tenant_id.
    Serializes values to JSON for cross-service compatibility.
    """

    def __init__(self, namespace: str, tenant_id: str) -> None:
        """
        Args:
            namespace: Logical namespace within the tenant (e.g., "voice", "llm")
            tenant_id: Tenant identifier for key isolation
        """
        self._namespace = namespace
        self._tenant_id = tenant_id

    def _key(self, key: str) -> str:
        """Build tenant-namespaced cache key."""
        return build_cache_key(self._tenant_id, self._namespace, key)

    async def get(self, key: str) -> Any | None:
        """
        Get a value from cache.

        Returns:
            Deserialized value if found, None if cache miss.
        """
        start = time.perf_counter()
        full_key = self._key(key)
        try:
            redis = await get_redis()
            raw = await redis.get(full_key)
            elapsed = (time.perf_counter() - start) * 1000

            CACHE_OPERATION_DURATION_SECONDS.labels(operation="get").observe(
                elapsed / 1000
            )

            if raw is None:
                CACHE_MISSES_TOTAL.labels(
                    namespace=self._namespace, operation="get"
                ).inc()
                return None

            CACHE_HITS_TOTAL.labels(
                namespace=self._namespace, operation="get"
            ).inc()
            return json.loads(raw)

        except RedisError as exc:
            CACHE_ERRORS_TOTAL.labels(
                namespace=self._namespace, error_type=type(exc).__name__
            ).inc()
            logger.warning(
                "cache_get_error",
                key=full_key,
                error=str(exc),
                namespace=self._namespace,
            )
            return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Set a value in cache with optional TTL.

        Args:
            key: Cache key (will be namespaced)
            value: Serializable value to store
            ttl: Time-to-live in seconds. Defaults to settings.redis_default_ttl.

        Returns:
            True if set successfully, False on error.
        """
        start = time.perf_counter()
        full_key = self._key(key)
        ttl_seconds = ttl or settings.redis_default_ttl
        try:
            redis = await get_redis()
            serialized = json.dumps(value, default=str)
            await redis.setex(full_key, ttl_seconds, serialized)
            elapsed = (time.perf_counter() - start) * 1000
            CACHE_OPERATION_DURATION_SECONDS.labels(operation="set").observe(
                elapsed / 1000
            )
            return True
        except RedisError as exc:
            CACHE_ERRORS_TOTAL.labels(
                namespace=self._namespace, error_type=type(exc).__name__
            ).inc()
            logger.warning("cache_set_error", key=full_key, error=str(exc))
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache. Returns True if key existed."""
        full_key = self._key(key)
        try:
            redis = await get_redis()
            deleted = await redis.delete(full_key)
            return bool(deleted)
        except RedisError as exc:
            CACHE_ERRORS_TOTAL.labels(
                namespace=self._namespace, error_type=type(exc).__name__
            ).inc()
            logger.warning("cache_delete_error", key=full_key, error=str(exc))
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        full_key = self._key(key)
        try:
            redis = await get_redis()
            result = await redis.exists(full_key)
            return bool(result)
        except RedisError:
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """Reset TTL on an existing key."""
        full_key = self._key(key)
        try:
            redis = await get_redis()
            return bool(await redis.expire(full_key, ttl))
        except RedisError:
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Atomic increment for counters (rate limiting, etc.)."""
        full_key = self._key(key)
        try:
            redis = await get_redis()
            return int(await redis.incrby(full_key, amount))
        except RedisError as exc:
            CACHE_ERRORS_TOTAL.labels(
                namespace=self._namespace, error_type=type(exc).__name__
            ).inc()
            raise


class DistributedLock:
    """
    Redis-based distributed lock (simplified Redlock for single cluster).

    Uses SET NX EX pattern with unique token for safe release.
    """

    def __init__(
        self,
        name: str,
        tenant_id: str,
        timeout: float = 30.0,
    ) -> None:
        self._key = build_cache_key(tenant_id, "lock", name)
        self._timeout = timeout
        self._token = str(uuid.uuid4())
        self._held = False

    async def acquire(self) -> bool:
        """
        Attempt to acquire the lock.

        Returns:
            True if lock acquired, False if already held by another process.
        """
        try:
            redis = await get_redis()
            result = await redis.set(
                self._key,
                self._token,
                nx=True,
                ex=int(self._timeout),
            )
            self._held = bool(result)
            return self._held
        except RedisError as exc:
            logger.warning("lock_acquire_error", key=self._key, error=str(exc))
            return False

    async def release(self) -> bool:
        """
        Release the lock atomically using Lua script.

        Only releases if the current process holds the lock (token match).
        """
        lua_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        try:
            redis = await get_redis()
            result = await redis.eval(lua_script, 1, self._key, self._token)
            self._held = False
            return bool(result)
        except RedisError as exc:
            logger.warning("lock_release_error", key=self._key, error=str(exc))
            return False

    async def __aenter__(self) -> "DistributedLock":
        """Acquire lock on context entry."""
        acquired = await self.acquire()
        if not acquired:
            raise RuntimeError(
                f"Could not acquire distributed lock: {self._key}"
            )
        return self

    async def __aexit__(self, *_: Any) -> None:
        """Release lock on context exit."""
        if self._held:
            await self.release()


@asynccontextmanager
async def distributed_lock(
    name: str, tenant_id: str, timeout: float = 30.0
) -> AsyncGenerator[DistributedLock, None]:
    """Context manager for distributed lock acquisition."""
    lock = DistributedLock(name, tenant_id, timeout)
    async with lock:
        yield lock
