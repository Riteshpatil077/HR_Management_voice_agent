"""
Application Use Cases for HR Service.

Orchestrates domain logic and infrastructure.
"""
from __future__ import annotations

import structlog

from services.hr_service.domain.models import Employee, ContactInfo, JobDetails, EmployeeStatus
from services.hr_service.infrastructure.repositories import EmployeeRepository
from shared.domain_events import EmployeeCreated, EmployeeUpdated
from shared.unit_of_work import UnitOfWork

logger = structlog.get_logger("hr_service.use_cases")

class CreateEmployeeUseCase:
    """Use case to create a new employee profile."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        department_id: str,
        position: str,
        status: EmployeeStatus = EmployeeStatus.ONBOARDING,
    ) -> str:
        """
        Create a new employee profile.
        """
        contact_info = ContactInfo(email=email, phone_number=phone_number)
        job_details = JobDetails(department_id=department_id, position=position)
        
        employee = Employee(
            tenant_id=tenant_id,
            first_name=first_name,
            last_name=last_name,
            contact_info=contact_info,
            job_details=job_details,
            status=status,
        )

        async with self.uow as uow:
            repo = EmployeeRepository(uow.session)
            repo.add(employee)
            
            # Emit Domain Event
            uow.collect_event(
                EmployeeCreated(
                    employee_id=employee.id,
                    department_id=department_id,
                    position=position,
                    tenant_id=tenant_id,
                )
            )
            await uow.commit()
            
        logger.info("employee_created", employee_id=employee.id, tenant_id=tenant_id)
        return employee.id


class UpdateEmployeeContactUseCase:
    """Use case to update employee contact details."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        employee_id: str,
        email: str,
        phone_number: str,
    ) -> None:
        """
        Update an employee's contact information.
        """
        async with self.uow as uow:
            repo = EmployeeRepository(uow.session)
            employee = await repo.get(employee_id)
            
            if not employee or employee.tenant_id != tenant_id:
                raise ValueError(f"Employee {employee_id} not found")
                
            new_contact = ContactInfo(email=email, phone_number=phone_number)
            employee.update_contact_info(new_contact)
            
            uow.collect_event(
                EmployeeUpdated(
                    employee_id=employee.id,
                    changed_fields=["contact_info"],
                    tenant_id=tenant_id,
                )
            )
            await uow.commit()
            
        logger.info("employee_contact_updated", employee_id=employee_id, tenant_id=tenant_id)
