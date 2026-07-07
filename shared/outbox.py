"""
Transactional Outbox Pattern.

RULE implementation: Guarantees that domain events are published
to the message broker exactly-once, even if the service crashes
between the database write and the queue publish.

Flow:
1. Business logic writes DB record + outbox entry in ONE transaction
2. Outbox relay worker reads unpublished entries
3. Worker publishes to RabbitMQ
4. Worker marks outbox entry as published

Design Pattern: Outbox + Relay Worker
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.settings import get_settings

logger = structlog.get_logger("outbox")
settings = get_settings()


class OutboxStatus(str, Enum):
    """Status of an outbox message."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class OutboxEntry:
    """A single outbox record awaiting publication."""

    id: str
    aggregate_type: str         # e.g., "Call", "Employee", "Interview"
    aggregate_id: str           # ID of the aggregate
    event_type: str             # e.g., "CallCompleted", "EmployeeCreated"
    payload: dict[str, Any]
    tenant_id: str
    queue_name: str
    routing_key: str
    status: OutboxStatus = OutboxStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime | None = None
    published_at: datetime | None = None


class OutboxWriter:
    """
    Writes outbox entries within an active database transaction.

    Usage (inside a Unit of Work):
        async with uow:
            employee = Employee(...)
            uow.session.add(employee)
            await outbox.write(
                session=uow.session,
                aggregate_type="Employee",
                aggregate_id=str(employee.id),
                event_type="EmployeeCreated",
                payload=employee.to_dict(),
                tenant_id=employee.tenant_id,
                queue_name="hr.events",
                routing_key="employee.created",
            )
            await uow.commit()
            # Both DB write and outbox entry are committed atomically
    """

    async def write(
        self,
        session: AsyncSession,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        tenant_id: str,
        queue_name: str,
        routing_key: str,
        max_retries: int = 3,
    ) -> OutboxEntry:
        """
        Write an outbox entry to the DB within the current session.

        MUST be called within an active transaction (the caller commits).
        """
        from sqlalchemy import text
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        await session.execute(
            text("""
                INSERT INTO outbox.messages (
                    id, aggregate_type, aggregate_id, event_type,
                    payload, tenant_id, queue_name, routing_key,
                    status, retry_count, max_retries, created_at
                ) VALUES (
                    :id, :aggregate_type, :aggregate_id, :event_type,
                    :payload, :tenant_id, :queue_name, :routing_key,
                    :status, 0, :max_retries, :created_at
                )
            """),
            {
                "id": entry_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "payload": json.dumps(payload, default=str),
                "tenant_id": tenant_id,
                "queue_name": queue_name,
                "routing_key": routing_key,
                "status": OutboxStatus.PENDING.value,
                "max_retries": max_retries,
                "created_at": now.isoformat(),
            },
        )

        logger.debug(
            "outbox_entry_written",
            entry_id=entry_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
        )

        return OutboxEntry(
            id=entry_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            tenant_id=tenant_id,
            queue_name=queue_name,
            routing_key=routing_key,
            created_at=now,
        )


class OutboxRelayWorker:
    """
    Background worker that publishes pending outbox entries.

    Polls the outbox table for PENDING entries and publishes them
    to RabbitMQ. Marks entries as PUBLISHED or FAILED accordingly.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent duplicate processing
    in multi-instance deployments.
    """

    def __init__(self, session_factory: Any, poll_interval: float = 1.0) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def start(self) -> None:
        """Start the relay worker background task."""
        self._running = True
        self._task = asyncio.create_task(
            self._relay_loop(), name="outbox-relay-worker"
        )
        logger.info("outbox_relay_started", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        """Stop the relay worker gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("outbox_relay_stopped")

    async def _relay_loop(self) -> None:
        """Main relay loop: poll → publish → mark → sleep."""
        while self._running:
            try:
                published_count = await self._process_pending()
                if published_count == 0:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("outbox_relay_error", error=str(exc))
                await asyncio.sleep(self._poll_interval)

    async def _process_pending(self) -> int:
        """
        Fetch and publish up to 50 pending outbox entries.

        Uses FOR UPDATE SKIP LOCKED for safe multi-instance processing.

        Returns:
            Number of entries processed.
        """
        from sqlalchemy import text

        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, aggregate_type, aggregate_id, event_type,
                           payload, tenant_id, queue_name, routing_key,
                           retry_count, max_retries
                    FROM outbox.messages
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 50
                    FOR UPDATE SKIP LOCKED
                """)
            )
            rows = result.fetchall()

            if not rows:
                return 0

            from shared.queue import QueueMessage, QueueName, publish_message

            published = 0
            for row in rows:
                entry_id = str(row.id)
                try:
                    payload = json.loads(row.payload)
                    await publish_message(
                        QueueMessage(
                            queue=QueueName(row.queue_name),
                            payload=payload,
                            tenant_id=row.tenant_id,
                            priority=5,
                        )
                    )
                    await session.execute(
                        text("""
                            UPDATE outbox.messages
                            SET status = 'published',
                                published_at = NOW()
                            WHERE id = :id
                        """),
                        {"id": entry_id},
                    )
                    published += 1

                except Exception as exc:
                    new_retry_count = int(row.retry_count) + 1
                    new_status = (
                        "failed"
                        if new_retry_count >= int(row.max_retries)
                        else "pending"
                    )
                    await session.execute(
                        text("""
                            UPDATE outbox.messages
                            SET retry_count = :retry_count,
                                status = :status
                            WHERE id = :id
                        """),
                        {
                            "id": entry_id,
                            "retry_count": new_retry_count,
                            "status": new_status,
                        },
                    )
                    logger.warning(
                        "outbox_publish_failed",
                        entry_id=entry_id,
                        event_type=row.event_type,
                        retry_count=new_retry_count,
                        error=str(exc),
                    )

            await session.commit()
            if published:
                logger.info("outbox_entries_published", count=published)
            return published


# ── Module singletons ──────────────────────────────────────────────────────────
_outbox_writer = OutboxWriter()


def get_outbox_writer() -> OutboxWriter:
    """Return the singleton outbox writer."""
    return _outbox_writer
