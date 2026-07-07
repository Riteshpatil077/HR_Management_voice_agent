"""
HR Service Domain Models.

Defines the core entities and value objects for the HR Service.
Follows Domain-Driven Design principles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

from services.hr_service.domain.exceptions import InvalidEmployeeStateError


class EmployeeStatus(str, Enum):
    """Lifecycle statuses for an employee."""
    CANDIDATE = "candidate"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


@dataclass
class ContactInfo:
    """Value object for employee contact details."""
    email: str
    phone_number: str
    address: str | None = None


@dataclass
class JobDetails:
    """Value object for job role and department."""
    department_id: str
    position: str
    manager_id: str | None = None
    start_date: date | None = None


class Employee:
    """
    Employee Aggregate Root.
    
    Manages the core identity and lifecycle of an employee within the system.
    """

    def __init__(
        self,
        tenant_id: str,
        first_name: str,
        last_name: str,
        contact_info: ContactInfo,
        job_details: JobDetails | None = None,
        employee_id: str | None = None,
        status: EmployeeStatus = EmployeeStatus.CANDIDATE,
    ) -> None:
        self.id = employee_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.first_name = first_name
        self.last_name = last_name
        self.contact_info = contact_info
        self.job_details = job_details
        self._status = status
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    @property
    def status(self) -> EmployeeStatus:
        return self._status
        
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def update_contact_info(self, new_contact: ContactInfo) -> None:
        self.contact_info = new_contact
        self.updated_at = datetime.now(timezone.utc)

    def assign_to_department(self, job_details: JobDetails) -> None:
        if self._status in (EmployeeStatus.TERMINATED, EmployeeStatus.SUSPENDED):
            raise InvalidEmployeeStateError(self._status.value, "assign_to_department")
        self.job_details = job_details
        self.updated_at = datetime.now(timezone.utc)

    def promote_to_active(self) -> None:
        if self._status != EmployeeStatus.ONBOARDING:
            raise InvalidEmployeeStateError(self._status.value, "promote_to_active")
        self._status = EmployeeStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)

    def terminate(self) -> None:
        self._status = EmployeeStatus.TERMINATED
        self.updated_at = datetime.now(timezone.utc)


class Department:
    """
    Department Entity.
    """

    def __init__(
        self,
        tenant_id: str,
        name: str,
        head_manager_id: str | None = None,
        department_id: str | None = None,
    ) -> None:
        self.id = department_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.name = name
        self.head_manager_id = head_manager_id
        self.created_at = datetime.now(timezone.utc)
