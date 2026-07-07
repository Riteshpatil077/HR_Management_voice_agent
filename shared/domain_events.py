"""
Domain Events infrastructure.

Domain events are facts about things that happened in the domain.
They are collected during a transaction and dispatched after commit.

Design Pattern: Domain Events + Observer/Event Bus
"""
from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable, Coroutine, TypeVar

import structlog

logger = structlog.get_logger("domain_events")
T = TypeVar("T", bound="DomainEvent")
AsyncHandler = Callable[[Any], Coroutine[Any, Any, None]]


@dataclass
class DomainEvent(ABC):
    """
    Base class for all domain events.

    Every event has a unique ID, timestamp, tenant context,
    and correlation ID for distributed tracing.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = ""
    correlation_id: str = ""

    @property
    @abstractmethod
    def event_type(self) -> str:
        """Return the event type string (e.g., 'voice.call.completed')."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to a plain dict for queue publishing."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "tenant_id": self.tenant_id,
            "correlation_id": self.correlation_id,
        }


# ── Voice Domain Events ────────────────────────────────────────────────────────
@dataclass
class CallInitiated(DomainEvent):
    call_id: str = ""
    candidate_phone: str = ""
    job_id: str = ""

    @property
    def event_type(self) -> str:
        return "voice.call.initiated"


@dataclass
class CallCompleted(DomainEvent):
    call_id: str = ""
    duration_seconds: int = 0
    outcome: str = ""
    transcript_url: str = ""

    @property
    def event_type(self) -> str:
        return "voice.call.completed"


@dataclass
class CallFailed(DomainEvent):
    call_id: str = ""
    reason: str = ""
    provider: str = ""

    @property
    def event_type(self) -> str:
        return "voice.call.failed"


@dataclass
class ConsentVerified(DomainEvent):
    call_id: str = ""
    consent_type: str = ""
    verified: bool = False

    @property
    def event_type(self) -> str:
        return "voice.consent.verified"


# ── HR Domain Events ────────────────────────────────────────────────────────────
@dataclass
class EmployeeCreated(DomainEvent):
    employee_id: str = ""
    department_id: str = ""
    position: str = ""

    @property
    def event_type(self) -> str:
        return "hr.employee.created"


@dataclass
class EmployeeUpdated(DomainEvent):
    employee_id: str = ""
    changed_fields: list[str] = field(default_factory=list)

    @property
    def event_type(self) -> str:
        return "hr.employee.updated"


# ── Interview Domain Events ─────────────────────────────────────────────────────
@dataclass
class InterviewScheduled(DomainEvent):
    interview_id: str = ""
    candidate_id: str = ""
    scheduled_at: str = ""
    interviewer_ids: list[str] = field(default_factory=list)

    @property
    def event_type(self) -> str:
        return "interview.scheduled"


@dataclass
class InterviewConfirmed(DomainEvent):
    interview_id: str = ""
    confirmed_via: str = ""

    @property
    def event_type(self) -> str:
        return "interview.confirmed"


@dataclass
class InterviewCancelled(DomainEvent):
    interview_id: str = ""
    reason: str = ""
    cancelled_by: str = ""

    @property
    def event_type(self) -> str:
        return "interview.cancelled"


# ── Onboarding Domain Events ────────────────────────────────────────────────────
@dataclass
class OnboardingStarted(DomainEvent):
    onboarding_id: str = ""
    employee_id: str = ""
    start_date: str = ""

    @property
    def event_type(self) -> str:
        return "onboarding.started"


@dataclass
class OnboardingTaskCompleted(DomainEvent):
    onboarding_id: str = ""
    task_id: str = ""
    task_name: str = ""

    @property
    def event_type(self) -> str:
        return "onboarding.task.completed"


# ── Event Bus ───────────────────────────────────────────────────────────────────
class EventBus:
    """
    In-process event bus for domain event dispatch.

    Handlers are registered per event type.
    Events are dispatched asynchronously after commit.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[AsyncHandler]] = {}

    def subscribe(self, event_type: str) -> Callable[[AsyncHandler], AsyncHandler]:
        """
        Decorator to subscribe a handler to an event type.

        Usage:
            @event_bus.subscribe("voice.call.completed")
            async def handle_call_completed(event: CallCompleted) -> None:
                await send_summary_whatsapp(event)
        """
        def decorator(handler: AsyncHandler) -> AsyncHandler:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            logger.debug(
                "event_handler_registered",
                event_type=event_type,
                handler=handler.__name__,
            )
            return handler
        return decorator

    async def dispatch(self, event: DomainEvent) -> None:
        """
        Dispatch an event to all registered handlers.

        Handlers run concurrently. Handler failures are logged but
        do not affect other handlers or the main request.
        """
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return

        logger.debug(
            "event_dispatching",
            event_type=event.event_type,
            event_id=event.event_id,
            handler_count=len(handlers),
        )

        results = await asyncio.gather(
            *[handler(event) for handler in handlers],
            return_exceptions=True,
        )

        for handler, result in zip(handlers, results):
            if isinstance(result, Exception):
                logger.error(
                    "event_handler_failed",
                    event_type=event.event_type,
                    handler=handler.__name__,
                    error=str(result),
                )


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    """Return the singleton event bus."""
    return EventBus()
