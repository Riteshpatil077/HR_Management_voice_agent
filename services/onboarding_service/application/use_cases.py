"""
Application Use Cases for Onboarding Service.

Orchestrates domain logic and infrastructure.
"""
from __future__ import annotations

import structlog

from services.onboarding_service.domain.models import OnboardingPlan, OnboardingTask
from services.onboarding_service.infrastructure.repositories import OnboardingRepository
from shared.domain_events import EventBase
from shared.unit_of_work import UnitOfWork

logger = structlog.get_logger("onboarding_service.use_cases")

# For demo purposes, we define a dummy event here, but usually it's in shared/domain_events.py
class OnboardingPlanCreated(EventBase):
    plan_id: str
    employee_id: str
    event_type: str = "OnboardingPlanCreated"

class CreateOnboardingPlanUseCase:
    """Use case to create an onboarding plan."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        employee_id: str,
        department_id: str,
    ) -> str:
        """
        Create a new onboarding plan with default tasks based on department.
        """
        # In a real system, you might fetch templates from the DB based on department_id
        tasks = [
            OnboardingTask(name="IT Setup", description="Laptop and email configuration"),
            OnboardingTask(name="HR Orientation", description="Benefits enrollment and policies"),
            OnboardingTask(name="Team Intro", description="Meet with the manager and team"),
        ]
        
        plan = OnboardingPlan(
            tenant_id=tenant_id,
            employee_id=employee_id,
            department_id=department_id,
            tasks=tasks,
        )

        async with self.uow as uow:
            repo = OnboardingRepository(uow.session)
            repo.add(plan)
            
            # Emit Domain Event
            uow.collect_event(
                OnboardingPlanCreated(
                    plan_id=plan.id,
                    employee_id=employee_id,
                    tenant_id=tenant_id,
                )
            )
            await uow.commit()
            
        logger.info("onboarding_plan_created", plan_id=plan.id, tenant_id=tenant_id)
        return plan.id
