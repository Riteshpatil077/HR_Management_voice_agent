"""
Interview Service Domain Models.

Defines the core entities and value objects for the Interview Service.
Follows Domain-Driven Design principles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from services.interview_service.domain.exceptions import InvalidInterviewStateError


class InterviewStatus(str, Enum):
    """Lifecycle statuses for an interview."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


@dataclass
class TimeSlot:
    """Value object representing a time window."""
    start_time: datetime
    end_time: datetime

    def __post_init__(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
            
    def conflicts_with(self, other: TimeSlot) -> bool:
        """Check if this time slot overlaps with another."""
        return max(self.start_time, other.start_time) < min(self.end_time, other.end_time)


@dataclass
class Participant:
    """Value object for an interview participant."""
    name: str
    email: str
    phone_number: str | None = None
    role: str = "candidate"  # candidate, interviewer


class Interview:
    """
    Interview Aggregate Root.
    
    Manages the lifecycle and scheduling of an interview.
    """

    def __init__(
        self,
        tenant_id: str,
        job_role: str,
        participants: list[Participant],
        time_slot: TimeSlot | None = None,
        interview_id: str | None = None,
        status: InterviewStatus = InterviewStatus.DRAFT,
    ) -> None:
        self.id = interview_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.job_role = job_role
        self.participants = participants
        self.time_slot = time_slot
        self._status = status
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.cancellation_reason: str | None = None
        self.meeting_link: str | None = None

    @property
    def status(self) -> InterviewStatus:
        return self._status

    def schedule(self, time_slot: TimeSlot) -> None:
        """Schedule the interview for a specific time slot."""
        if self._status not in (InterviewStatus.DRAFT, InterviewStatus.SCHEDULED):
            raise InvalidInterviewStateError(self._status.value, "schedule")
        self.time_slot = time_slot
        self._status = InterviewStatus.SCHEDULED
        self.updated_at = datetime.now(timezone.utc)

    def confirm(self, meeting_link: str | None = None) -> None:
        """Confirm the interview (e.g., after candidate accepts calendar invite)."""
        if self._status != InterviewStatus.SCHEDULED:
            raise InvalidInterviewStateError(self._status.value, "confirm")
        self._status = InterviewStatus.CONFIRMED
        if meeting_link:
            self.meeting_link = meeting_link
        self.updated_at = datetime.now(timezone.utc)

    def cancel(self, reason: str) -> None:
        """Cancel the interview."""
        if self._status in (InterviewStatus.COMPLETED, InterviewStatus.CANCELLED):
            raise InvalidInterviewStateError(self._status.value, "cancel")
        self._status = InterviewStatus.CANCELLED
        self.cancellation_reason = reason
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark the interview as completed."""
        if self._status != InterviewStatus.CONFIRMED:
            raise InvalidInterviewStateError(self._status.value, "mark_completed")
        self._status = InterviewStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)
