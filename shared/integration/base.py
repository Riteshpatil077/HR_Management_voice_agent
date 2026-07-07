"""
Base integration layer.

All external provider calls MUST go through this layer.
Direct API calls in business logic are forbidden (RULE 16).

Design Pattern: Adapter + Strategy + Circuit Breaker + Bulkhead
"""
from __future__ import annotations

import abc
import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

import structlog

from shared.circuit_breaker import CircuitBreaker, get_breaker
from shared.cost_tracker import CostEvent, track_cost
from shared.metrics import (
    INTEGRATION_ERRORS,
    INTEGRATION_LATENCY,
    INTEGRATION_REQUESTS,
)
from shared.settings import get_settings

logger = structlog.get_logger("integration.base")
settings = get_settings()

T = TypeVar("T")


class ProviderStatus(Enum):
    """Health status of an external provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    """Snapshot of a provider's health state."""

    provider: str
    status: ProviderStatus
    latency_ms: float
    error_rate: float
    last_checked: float = field(default_factory=time.monotonic)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationRequest(Generic[T]):
    """Typed request envelope for any integration call."""

    provider: str
    operation: str
    payload: T
    tenant_id: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    priority: int = 5


@dataclass
class IntegrationResponse(Generic[T]):
    """Typed response envelope from any integration call."""

    provider: str
    operation: str
    data: T
    latency_ms: float
    cost_usd: float = 0.0
    tokens_used: int = 0
    correlation_id: str = ""
    cached: bool = False


class RetryPolicy:
    """
    Exponential backoff retry policy with jitter.

    Applied automatically by BaseAdapter.execute().
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

    def delay(self, attempt: int) -> float:
        """Calculate delay for attempt N with exponential backoff."""
        import random
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        if self.jitter:
            delay *= 0.5 + random.random() * 0.5
        return delay


class BaseAdapter(abc.ABC, Generic[T]):
    """
    Abstract base for all external provider adapters.

    Responsibilities:
    - Provider-specific API call implementation
    - Health check endpoint
    - Cost calculation
    - API version management

    All concrete adapters MUST inherit from this class.
    All external calls MUST go through self.execute().
    """

    provider_name: str = "unknown"
    api_version: str = "v1"

    def __init__(self) -> None:
        self._breaker: CircuitBreaker = get_breaker(
            self.provider_name,
            failure_threshold=5,
            recovery_timeout=30,
        )
        self._retry_policy = RetryPolicy(max_retries=3)
        self._semaphore = asyncio.Semaphore(50)  # Bulkhead: max 50 concurrent

    @abc.abstractmethod
    async def _call(self, request: IntegrationRequest[Any]) -> Any:
        """Execute the provider-specific API call."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return current health status of this provider."""
        ...

    @abc.abstractmethod
    def calculate_cost(self, response_data: Any) -> float:
        """Calculate cost in USD for this API call."""
        ...

    async def execute(
        self, request: IntegrationRequest[Any]
    ) -> IntegrationResponse[Any]:
        """
        Execute with circuit breaker + bulkhead + retry + cost tracking.

        This is the ONLY public method callers should use for raw execution.
        """
        async with self._semaphore:
            return await self._execute_with_retry(request)

    async def _execute_with_retry(
        self, request: IntegrationRequest[Any]
    ) -> IntegrationResponse[Any]:
        """Inner execution loop with retry policy."""
        last_error: Exception | None = None
        for attempt in range(self._retry_policy.max_retries + 1):
            try:
                start = time.perf_counter()
                
                # Execute within circuit breaker and timeout
                data = await asyncio.wait_for(
                    self._breaker.call(self._call, request),
                    timeout=request.timeout_seconds,
                )
                
                latency_ms = round((time.perf_counter() - start) * 1000, 2)
                cost = self.calculate_cost(data)

                INTEGRATION_REQUESTS.labels(
                    provider=self.provider_name,
                    operation=request.operation,
                    status="success",
                ).inc()
                
                INTEGRATION_LATENCY.labels(
                    provider=self.provider_name,
                    operation=request.operation,
                ).observe(latency_ms)

                await track_cost(
                    CostEvent(
                        provider=self.provider_name,
                        operation=request.operation,
                        tenant_id=request.tenant_id,
                        cost_usd=cost,
                        correlation_id=request.correlation_id,
                    )
                )

                logger.info(
                    "integration_success",
                    provider=self.provider_name,
                    operation=request.operation,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    correlation_id=request.correlation_id,
                )
                
                return IntegrationResponse(
                    provider=self.provider_name,
                    operation=request.operation,
                    data=data,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    correlation_id=request.correlation_id,
                )

            except asyncio.TimeoutError as exc:
                last_error = exc
                INTEGRATION_ERRORS.labels(
                    provider=self.provider_name,
                    operation=request.operation,
                    error_type="timeout",
                ).inc()
                logger.warning(
                    "integration_timeout",
                    provider=self.provider_name,
                    attempt=attempt,
                    timeout=request.timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                INTEGRATION_ERRORS.labels(
                    provider=self.provider_name,
                    operation=request.operation,
                    error_type=type(exc).__name__,
                ).inc()
                logger.warning(
                    "integration_error",
                    provider=self.provider_name,
                    attempt=attempt,
                    error=str(exc),
                )

            if attempt < self._retry_policy.max_retries:
                delay = self._retry_policy.delay(attempt)
                logger.info(
                    "integration_retry",
                    provider=self.provider_name,
                    attempt=attempt + 1,
                    delay_s=round(delay, 2),
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Provider {self.provider_name} failed after "
            f"{self._retry_policy.max_retries + 1} attempts: {last_error}"
        )
