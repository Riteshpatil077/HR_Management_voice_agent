"""
LLM cost tracking.

RULE 25: Cost tracking on every LLM call, voice API call, and storage op.

All external API cost events are:
1. Emitted as Prometheus counters (real-time)
2. Written to PostgreSQL analytics table (historical)
3. Aggregated per tenant for billing

Design Pattern: Event Sourcing for cost events.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from queue import Queue
from typing import Any

import structlog

from shared.metrics import COST_USD_TOTAL
from shared.settings import get_settings

logger = structlog.get_logger("cost_tracker")
settings = get_settings()


@dataclass
class CostEvent:
    """Immutable cost event for a single external API call."""

    provider: str           # e.g., "openai", "deepgram", "elevenlabs", "s3"
    operation: str          # e.g., "chat_completion", "transcribe", "synthesize"
    tenant_id: str
    cost_usd: float
    correlation_id: str = ""
    call_id: str | None = None      # Voice call ID if applicable
    model: str | None = None        # LLM model name
    input_tokens: int = 0           # LLM input tokens
    output_tokens: int = 0          # LLM output tokens
    duration_seconds: float = 0.0   # Audio duration for STT/TTS
    bytes_processed: int = 0        # S3 bytes stored/transferred
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Validate cost event fields."""
        if self.cost_usd < 0:
            raise ValueError(f"Cost cannot be negative: {self.cost_usd}")
        if not self.tenant_id:
            raise ValueError("tenant_id is required for cost tracking")


# In-memory buffer for async DB writes
_cost_queue: asyncio.Queue[CostEvent] = asyncio.Queue(maxsize=10000)
_flush_task: asyncio.Task | None = None  # type: ignore[type-arg]


async def track_cost(event: CostEvent) -> None:
    """
    Record a cost event.

    Immediately updates Prometheus counter (synchronous).
    Enqueues for async PostgreSQL write (non-blocking).

    Args:
        event: The cost event to record.
    """
    if not settings.feature_cost_tracking_enabled:
        return

    # Prometheus counter — immediate, non-blocking
    COST_USD_TOTAL.labels(
        provider=event.provider,
        operation_type=event.operation,
        tenant_id=event.tenant_id,
    ).inc(event.cost_usd)

    logger.info(
        "cost_event",
        provider=event.provider,
        operation=event.operation,
        tenant_id=event.tenant_id,
        cost_usd=round(event.cost_usd, 6),
        model=event.model,
        input_tokens=event.input_tokens,
        output_tokens=event.output_tokens,
        correlation_id=event.correlation_id,
    )

    # Queue for async DB persistence (non-blocking)
    try:
        _cost_queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning(
            "cost_queue_full",
            provider=event.provider,
            cost_usd=event.cost_usd,
        )


async def start_cost_flush_worker(db_session_factory: Any) -> asyncio.Task:  # type: ignore[type-arg]
    """
    Start the background worker that flushes cost events to PostgreSQL.

    Args:
        db_session_factory: SQLAlchemy async session factory

    Returns:
        The background task (store to cancel on shutdown).
    """
    global _flush_task

    async def _flush_loop() -> None:
        while True:
            batch: list[CostEvent] = []
            try:
                # Batch collect up to 100 events or wait 5 seconds
                deadline = time.monotonic() + 5.0
                while len(batch) < 100 and time.monotonic() < deadline:
                    try:
                        event = await asyncio.wait_for(
                            _cost_queue.get(), timeout=max(0, deadline - time.monotonic())
                        )
                        batch.append(event)
                    except asyncio.TimeoutError:
                        break

                if not batch:
                    continue

                await _flush_batch_to_db(batch, db_session_factory)
                logger.debug(
                    "cost_events_flushed",
                    count=len(batch),
                    total_usd=round(sum(e.cost_usd for e in batch), 6),
                )

            except asyncio.CancelledError:
                # Flush remaining events before shutdown
                if batch:
                    await _flush_batch_to_db(batch, db_session_factory)
                break
            except Exception as exc:
                logger.error("cost_flush_error", error=str(exc))
                await asyncio.sleep(1)

    _flush_task = asyncio.create_task(_flush_loop(), name="cost-flush-worker")
    return _flush_task


async def _flush_batch_to_db(
    events: list[CostEvent], session_factory: Any
) -> None:
    """Write a batch of cost events to the PostgreSQL analytics table."""
    if not events:
        return

    try:
        async with session_factory() as session:
            from sqlalchemy import text
            rows = [
                {
                    "provider": e.provider,
                    "operation": e.operation,
                    "tenant_id": e.tenant_id,
                    "cost_usd": e.cost_usd,
                    "correlation_id": e.correlation_id,
                    "call_id": e.call_id,
                    "model": e.model,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "duration_seconds": e.duration_seconds,
                    "bytes_processed": e.bytes_processed,
                    "recorded_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(e.timestamp)
                    ),
                }
                for e in events
            ]
            await session.execute(
                text("""
                    INSERT INTO analytics.api_costs (
                        provider, operation, tenant_id, cost_usd,
                        correlation_id, call_id, model,
                        input_tokens, output_tokens,
                        duration_seconds, bytes_processed, recorded_at
                    ) VALUES (
                        :provider, :operation, :tenant_id, :cost_usd,
                        :correlation_id, :call_id, :model,
                        :input_tokens, :output_tokens,
                        :duration_seconds, :bytes_processed, :recorded_at
                    )
                """),
                rows,
            )
            await session.commit()
    except Exception as exc:
        logger.error(
            "cost_db_write_failed",
            error=str(exc),
            batch_size=len(events),
        )


async def stop_cost_flush_worker() -> None:
    """Cancel the cost flush worker and await cleanup."""
    global _flush_task
    if _flush_task and not _flush_task.done():
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
    logger.info("cost_flush_worker_stopped")
