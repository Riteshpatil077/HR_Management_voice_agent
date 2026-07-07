"""
Voice Service Domain Models.

Defines the core entities and value objects for the Voice Service.
Follows Domain-Driven Design principles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from services.voice_service.domain.exceptions import InvalidCallStateTransitionError


class CallState(str, Enum):
    """Finite State Machine states for a Call."""
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CallParticipant:
    """Value object representing a call participant."""
    phone_number: str
    role: str  # e.g., "candidate", "employee"
    id: str | None = None


@dataclass
class CallContext:
    """Value object holding contextual data for the LLM."""
    prompt_name: str
    prompt_version: str
    variables: dict[str, str] = field(default_factory=dict)
    expected_intent: str | None = None


class Call:
    """
    Call Aggregate Root.
    
    Manages the lifecycle of a voice interaction.
    """

    def __init__(
        self,
        tenant_id: str,
        participant: CallParticipant,
        context: CallContext,
        call_id: str | None = None,
        state: CallState = CallState.INITIATED,
    ) -> None:
        self.id = call_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.participant = participant
        self.context = context
        self._state = state
        self.created_at = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.ended_at: datetime | None = None
        self.recording_url: str | None = None
        self.provider_call_id: str | None = None
        self.failure_reason: str | None = None

    @property
    def state(self) -> CallState:
        return self._state

    def mark_ringing(self, provider_call_id: str) -> None:
        """Transition to ringing state."""
        if self._state != CallState.INITIATED:
            raise InvalidCallStateTransitionError(self._state.value, CallState.RINGING.value)
        self._state = CallState.RINGING
        self.provider_call_id = provider_call_id

    def mark_in_progress(self) -> None:
        """Transition to in-progress state."""
        if self._state not in (CallState.INITIATED, CallState.RINGING):
            raise InvalidCallStateTransitionError(self._state.value, CallState.IN_PROGRESS.value)
        self._state = CallState.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, recording_url: str | None = None) -> None:
        """Transition to completed state."""
        if self._state != CallState.IN_PROGRESS:
            raise InvalidCallStateTransitionError(self._state.value, CallState.COMPLETED.value)
        self._state = CallState.COMPLETED
        self.ended_at = datetime.now(timezone.utc)
        self.recording_url = recording_url

    def mark_failed(self, reason: str) -> None:
        """Transition to failed state."""
        self._state = CallState.FAILED
        self.ended_at = datetime.now(timezone.utc)
        self.failure_reason = reason

    @property
    def duration_seconds(self) -> int:
        """Calculate call duration in seconds."""
        if not self.started_at or not self.ended_at:
            return 0
        return int((self.ended_at - self.started_at).total_seconds())
