"""
Async circuit breaker implementation.

Prevents cascade failures by tracking provider error rates and
automatically stopping calls to unhealthy providers.

States:
- CLOSED: Normal operation. All calls pass through.
- OPEN: Provider failed. All calls rejected immediately.
- HALF_OPEN: Recovery probe. One call allowed to test recovery.

Design Pattern: Circuit Breaker (Nygard)
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar
from functools import lru_cache

import structlog

from shared.metrics import (
    INTEGRATION_CIRCUIT_BREAKER_STATE,
    INTEGRATION_CIRCUIT_BREAKER_TRIPS,
)

logger = structlog.get_logger("circuit_breaker")
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject all calls
    HALF_OPEN = "half_open" # Recovery probe


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, provider: str, recovery_in: float) -> None:
        super().__init__(
            f"Circuit breaker OPEN for provider '{provider}'. "
            f"Recovery probe in {recovery_in:.1f}s."
        )
        self.provider = provider
        self.recovery_in = recovery_in


class CircuitBreaker:
    """
    Async circuit breaker with automatic state transitions.

    Thread-safe for use in async contexts via asyncio.Lock.
    Emits Prometheus metrics on state changes.
    """

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ) -> None:
        """
        Initialize the circuit breaker.

        Args:
            provider: Name of the external provider (for metrics/logging)
            failure_threshold: Consecutive failures before OPEN transition
            recovery_timeout: Seconds in OPEN state before HALF_OPEN probe
            half_open_max_calls: Max concurrent calls in HALF_OPEN state
            success_threshold: Successes in HALF_OPEN before CLOSED transition
        """
        self.provider = provider
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

        self._update_state_metric()

    @property
    def state(self) -> CircuitState:
        """Return current circuit state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Return True if circuit is OPEN (rejecting calls)."""
        return self._state == CircuitState.OPEN

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute function through the circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments to pass to func
            **kwargs: Keyword arguments to pass to func

        Returns:
            Result of func(*args, **kwargs)

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN
            Exception: Any exception raised by func
        """
        await self._check_state()

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as exc:
            await self._on_failure(exc)
            raise

    async def _check_state(self) -> None:
        """
        Check current state and raise if circuit is OPEN.

        Transitions OPEN → HALF_OPEN when recovery timeout elapsed.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    if self._half_open_calls < self._half_open_max_calls:
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls += 1
                        self._success_count = 0
                        self._update_state_metric()
                        logger.info(
                            "circuit_breaker_half_open",
                            provider=self.provider,
                            elapsed_s=round(elapsed, 1),
                        )
                        return
                recovery_in = self._recovery_timeout - elapsed
                raise CircuitBreakerOpenError(self.provider, recovery_in)

    async def _on_success(self) -> None:
        """Handle successful call — potentially close the circuit."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)
                if self._success_count >= self._success_threshold:
                    self._transition_to_closed()
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset on any success

    async def _on_failure(self, exc: Exception) -> None:
        """Handle failed call — potentially open the circuit."""
        async with self._lock:
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — back to OPEN
                self._transition_to_open()
                logger.warning(
                    "circuit_breaker_half_open_failed",
                    provider=self.provider,
                    error=str(exc),
                )
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._transition_to_open()

    def _transition_to_open(self) -> None:
        """Transition to OPEN state. Must be called within lock."""
        self._state = CircuitState.OPEN
        self._half_open_calls = 0
        self._update_state_metric()
        INTEGRATION_CIRCUIT_BREAKER_TRIPS.labels(provider=self.provider).inc()
        logger.error(
            "circuit_breaker_opened",
            provider=self.provider,
            failure_count=self._failure_count,
            recovery_timeout_s=self._recovery_timeout,
        )

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state. Must be called within lock."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._update_state_metric()
        logger.info(
            "circuit_breaker_closed",
            provider=self.provider,
            after_success_count=self._success_threshold,
        )

    def _update_state_metric(self) -> None:
        """Update Prometheus gauge for circuit breaker state."""
        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.HALF_OPEN: 1,
            CircuitState.OPEN: 2,
        }[self._state]
        INTEGRATION_CIRCUIT_BREAKER_STATE.labels(
            provider=self.provider
        ).set(state_value)

    def reset(self) -> None:
        """
        Manually reset circuit to CLOSED state.

        Used in tests and emergency operational runbooks.
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._update_state_metric()
        logger.info("circuit_breaker_reset", provider=self.provider)

    def stats(self) -> dict[str, Any]:
        """Return current circuit breaker statistics."""
        return {
            "provider": self.provider,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_elapsed_s": (
                round(time.monotonic() - self._last_failure_time, 1)
                if self._last_failure_time
                else None
            ),
            "recovery_timeout_s": self._recovery_timeout,
            "failure_threshold": self._failure_threshold,
        }


# ── Global Registry ────────────────────────────────────────────────────────────
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()


def get_breaker(
    provider: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """
    Get or create a circuit breaker for the given provider.

    Returns the same instance for the same provider name (singleton per provider).
    Thread-safe via module-level dict (GIL-protected for reads in CPython).
    """
    if provider not in _breakers:
        _breakers[provider] = CircuitBreaker(
            provider=provider,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[provider]


def get_all_breaker_stats() -> list[dict[str, Any]]:
    """Return stats for all registered circuit breakers."""
    return [b.stats() for b in _breakers.values()]
