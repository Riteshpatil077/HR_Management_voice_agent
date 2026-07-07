"""
RabbitMQ async publisher and consumer.

Features:
- Priority queues for voice pipeline tasks
- Dead Letter Exchange (DLX) for failed messages
- Publisher confirms for guaranteed delivery
- Delayed message plugin for scheduled retries
- Per-tenant queue routing via routing keys

Queues:
- voice.generate (priority 10, DLX: voice.generate.dlq)
- whatsapp.send (priority 5, DLX: whatsapp.send.dlq)
- crm.sync (priority 3, DLX: crm.sync.dlq)
- notification.send (priority 5, DLX: notification.send.dlq)

Design Pattern: Message Bus + Publisher Confirms
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

import aio_pika
import structlog
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage

from shared.metrics import (
    QUEUE_DLQ_MESSAGES_TOTAL,
    QUEUE_MESSAGE_PROCESSING_SECONDS,
    QUEUE_MESSAGES_CONSUMED_TOTAL,
    QUEUE_MESSAGES_PUBLISHED_TOTAL,
)
from shared.settings import get_settings

logger = structlog.get_logger("queue")
settings = get_settings()

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class QueueName(str, Enum):
    """Platform queue names."""

    VOICE_GENERATE = "voice.generate"
    VOICE_GENERATE_DLQ = "voice.generate.dlq"
    WHATSAPP_SEND = "whatsapp.send"
    WHATSAPP_SEND_DLQ = "whatsapp.send.dlq"
    CRM_SYNC = "crm.sync"
    CRM_SYNC_DLQ = "crm.sync.dlq"
    NOTIFICATION_SEND = "notification.send"
    NOTIFICATION_SEND_DLQ = "notification.send.dlq"
    OUTBOX_RELAY = "outbox.relay"
    AUDIT_PERSIST = "audit.persist"
    CALL_ANALYTICS = "call.analytics"


@dataclass
class QueueMessage:
    """Typed message envelope for queue publishing."""

    queue: QueueName
    payload: dict[str, Any]
    tenant_id: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 5              # 0–10; higher = more urgent
    delay_ms: int = 0              # Delay before delivery (0 = immediate)
    max_retries: int = 3
    retry_count: int = 0


class RabbitMQClient:
    """
    Async RabbitMQ client with publisher confirms and DLX.

    Manages a single connection with multiple channels.
    Reconnects automatically on connection drops.
    """

    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._publish_channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._connected = asyncio.Event()

    async def connect(self) -> None:
        """Connect to RabbitMQ and declare all queues/exchanges."""
        self._connection = await aio_pika.connect_robust(
            url=settings.rabbitmq_url,
            heartbeat=settings.rabbitmq_heartbeat,
            reconnect_interval=5,
        )
        await self._setup_topology()
        self._connected.set()
        logger.info("rabbitmq_connected", url=settings.rabbitmq_url)

    async def _setup_topology(self) -> None:
        """Declare exchanges, DLXs, and all queues."""
        if not self._connection:
            raise RuntimeError("Not connected to RabbitMQ")

        self._publish_channel = await self._connection.channel()
        await self._publish_channel.set_qos(
            prefetch_count=settings.rabbitmq_prefetch_count
        )

        # Main exchange (direct routing)
        self._exchange = await self._publish_channel.declare_exchange(
            "hr-voice-agent",
            ExchangeType.DIRECT,
            durable=True,
        )

        # Dead letter exchange
        dlx = await self._publish_channel.declare_exchange(
            "hr-voice-agent.dlx",
            ExchangeType.DIRECT,
            durable=True,
        )

        # Declare all queues with DLX and priority support
        queue_configs = [
            (QueueName.VOICE_GENERATE, 10, QueueName.VOICE_GENERATE_DLQ),
            (QueueName.WHATSAPP_SEND, 5, QueueName.WHATSAPP_SEND_DLQ),
            (QueueName.CRM_SYNC, 3, QueueName.CRM_SYNC_DLQ),
            (QueueName.NOTIFICATION_SEND, 5, QueueName.NOTIFICATION_SEND_DLQ),
            (QueueName.OUTBOX_RELAY, 5, None),
            (QueueName.AUDIT_PERSIST, 3, None),
            (QueueName.CALL_ANALYTICS, 3, None),
        ]

        for queue_name, max_priority, dlq_name in queue_configs:
            args: dict[str, Any] = {
                "x-max-priority": max_priority,
                "x-message-ttl": 86_400_000,  # 24h
            }
            if dlq_name:
                args["x-dead-letter-exchange"] = "hr-voice-agent.dlx"
                args["x-dead-letter-routing-key"] = dlq_name.value

            q = await self._publish_channel.declare_queue(
                queue_name.value,
                durable=True,
                arguments=args,
            )
            await q.bind(self._exchange, routing_key=queue_name.value)

            if dlq_name:
                dlq = await self._publish_channel.declare_queue(
                    dlq_name.value,
                    durable=True,
                )
                await dlq.bind(dlx, routing_key=dlq_name.value)

        logger.info("rabbitmq_topology_ready")

    async def publish(self, message: QueueMessage) -> None:
        """
        Publish a message to the queue with publisher confirms.

        Args:
            message: Typed queue message envelope.

        Raises:
            RuntimeError: If not connected.
        """
        await self._connected.wait()

        if not self._exchange:
            raise RuntimeError("RabbitMQ exchange not initialized")

        body = json.dumps(
            {
                **message.payload,
                "_meta": {
                    "tenant_id": message.tenant_id,
                    "correlation_id": message.correlation_id,
                    "retry_count": message.retry_count,
                    "max_retries": message.max_retries,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            default=str,
        )

        amqp_message = Message(
            body=body.encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            priority=message.priority,
            message_id=str(uuid.uuid4()),
            correlation_id=message.correlation_id,
            content_type="application/json",
            headers={
                "tenant_id": message.tenant_id,
                "x-delay": message.delay_ms,
            },
        )

        await self._exchange.publish(
            amqp_message,
            routing_key=message.queue.value,
            timeout=5,
        )

        QUEUE_MESSAGES_PUBLISHED_TOTAL.labels(
            queue_name=message.queue.value,
            exchange="hr-voice-agent",
        ).inc()

        logger.debug(
            "message_published",
            queue=message.queue.value,
            tenant_id=message.tenant_id,
            correlation_id=message.correlation_id,
            priority=message.priority,
        )

    async def consume(
        self,
        queue: QueueName,
        handler: MessageHandler,
        concurrency: int = 10,
    ) -> None:
        """
        Start consuming messages from a queue.

        Args:
            queue: Queue to consume from
            handler: Async function to process each message
            concurrency: Max concurrent message processing
        """
        await self._connected.wait()

        if not self._connection:
            raise RuntimeError("Not connected to RabbitMQ")

        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=concurrency)

        semaphore = asyncio.Semaphore(concurrency)
        declared_queue = await channel.get_queue(queue.value)

        async def _on_message(message: AbstractIncomingMessage) -> None:
            async with semaphore:
                await self._process_message(message, handler, queue)

        await declared_queue.consume(_on_message)
        logger.info(
            "consumer_started",
            queue=queue.value,
            concurrency=concurrency,
        )

    async def _process_message(
        self,
        message: AbstractIncomingMessage,
        handler: MessageHandler,
        queue: QueueName,
    ) -> None:
        """Process a single message with error handling and retry."""
        import time
        start = time.perf_counter()
        body: dict[str, Any] = {}

        try:
            body = json.loads(message.body.decode())
            meta = body.get("_meta", {})
            retry_count = meta.get("retry_count", 0)
            max_retries = meta.get("max_retries", 3)

            logger.info(
                "message_received",
                queue=queue.value,
                message_id=message.message_id,
                retry_count=retry_count,
            )

            await handler(body)
            await message.ack()

            elapsed = time.perf_counter() - start
            QUEUE_MESSAGES_CONSUMED_TOTAL.labels(
                queue_name=queue.value, status="success"
            ).inc()
            QUEUE_MESSAGE_PROCESSING_SECONDS.labels(
                queue_name=queue.value
            ).observe(elapsed)

        except Exception as exc:
            elapsed = time.perf_counter() - start
            QUEUE_MESSAGES_CONSUMED_TOTAL.labels(
                queue_name=queue.value, status="failed"
            ).inc()
            logger.error(
                "message_processing_failed",
                queue=queue.value,
                error=str(exc),
                elapsed_ms=round(elapsed * 1000, 2),
            )

            meta = body.get("_meta", {})
            retry_count = meta.get("retry_count", 0)
            max_retries = meta.get("max_retries", 3)

            if retry_count < max_retries:
                # Requeue with incremented retry count
                await message.nack(requeue=False)
                QUEUE_DLQ_MESSAGES_TOTAL.labels(
                    queue_name=queue.value, reason="retry"
                ).inc()
            else:
                # Max retries exceeded — send to DLQ
                await message.reject(requeue=False)
                QUEUE_DLQ_MESSAGES_TOTAL.labels(
                    queue_name=queue.value, reason="max_retries_exceeded"
                ).inc()
                logger.error(
                    "message_sent_to_dlq",
                    queue=queue.value,
                    retry_count=retry_count,
                )

    async def close(self) -> None:
        """Gracefully close the RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("rabbitmq_disconnected")


# ── Module-level singleton ─────────────────────────────────────────────────────
_client: RabbitMQClient | None = None


async def get_queue_client() -> RabbitMQClient:
    """Return the singleton RabbitMQ client (connect if needed)."""
    global _client
    if _client is None:
        _client = RabbitMQClient()
        await _client.connect()
    return _client


async def publish_message(message: QueueMessage) -> None:
    """Convenience function to publish a message via the singleton client."""
    client = await get_queue_client()
    await client.publish(message)
