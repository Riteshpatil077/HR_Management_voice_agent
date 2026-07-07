"""
Onboarding Service Domain Models.

Defines the core entities and value objects for the Onboarding Service.
Follows Domain-Driven Design principles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from services.onboarding_service.domain.exceptions import (
    InvalidOnboardingStateError,
    TaskNotFoundError,
)


class OnboardingStatus(str, Enum):
    """Lifecycle statuses for an onboarding plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """Lifecycle statuses for an individual onboarding task."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OnboardingTask:
    """Entity representing a single task in an onboarding plan."""
    name: str
    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    completed_at: datetime | None = None
    
    def complete(self) -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)


class OnboardingPlan:
    """
    Onboarding Plan Aggregate Root.
    
    Manages a sequence of tasks for a new employee.
    """

    def __init__(
        self,
        tenant_id: str,
        employee_id: str,
        department_id: str,
        tasks: list[OnboardingTask],
        plan_id: str | None = None,
        status: OnboardingStatus = OnboardingStatus.PENDING,
    ) -> None:
        self.id = plan_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.employee_id = employee_id
        self.department_id = department_id
        self.tasks = tasks
        self._status = status
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None

    @property
    def status(self) -> OnboardingStatus:
        return self._status

    def start(self) -> None:
        """Start the onboarding process."""
        if self._status != OnboardingStatus.PENDING:
            raise InvalidOnboardingStateError(self._status.value, "start")
        self._status = OnboardingStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def complete_task(self, task_id: str) -> None:
        """Mark a specific task as completed."""
        if self._status != OnboardingStatus.IN_PROGRESS:
            raise InvalidOnboardingStateError(self._status.value, "complete_task")
            
        task = next((t for t in self.tasks if t.id == task_id), None)
        if not task:
            raise TaskNotFoundError(task_id)
            
        task.complete()
        self.updated_at = datetime.now(timezone.utc)
        
        # Check if all tasks are complete
        if all(t.status == TaskStatus.COMPLETED for t in self.tasks):
            self._status = OnboardingStatus.COMPLETED
            self.completed_at = datetime.now(timezone.utc)

    def cancel(self) -> None:
        """Cancel the onboarding plan."""
        if self._status in (OnboardingStatus.COMPLETED, OnboardingStatus.CANCELLED):
            raise InvalidOnboardingStateError(self._status.value, "cancel")
        self._status = OnboardingStatus.CANCELLED
        self.updated_at = datetime.now(timezone.utc)
