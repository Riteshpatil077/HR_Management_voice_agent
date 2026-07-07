"""
Application Use Cases for Interview Service.

Orchestrates domain logic and infrastructure.
"""
from __future__ import annotations

import structlog
from datetime import datetime

from services.interview_service.domain.models import Interview, Participant, TimeSlot, InterviewStatus
from services.interview_service.infrastructure.repositories import InterviewRepository
from shared.domain_events import InterviewScheduled, InterviewCancelled
from shared.unit_of_work import UnitOfWork

logger = structlog.get_logger("interview_service.use_cases")

class ScheduleInterviewUseCase:
    """Use case to schedule a new interview."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        job_role: str,
        candidate_name: str,
        candidate_email: str,
        interviewer_names: list[str],
        interviewer_emails: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """
        Create and schedule an interview.
        """
        participants = [
            Participant(name=candidate_name, email=candidate_email, role="candidate")
        ]
        for name, email in zip(interviewer_names, interviewer_emails):
            participants.append(Participant(name=name, email=email, role="interviewer"))
            
        time_slot = TimeSlot(start_time=start_time, end_time=end_time)
        
        interview = Interview(
            tenant_id=tenant_id,
            job_role=job_role,
            participants=participants,
        )
        
        interview.schedule(time_slot)

        async with self.uow as uow:
            repo = InterviewRepository(uow.session)
            repo.add(interview)
            
            # Emit Domain Event
            uow.collect_event(
                InterviewScheduled(
                    interview_id=interview.id,
                    candidate_id=candidate_email, # using email as ID for demo
                    scheduled_at=time_slot.start_time.isoformat(),
                    interviewer_ids=interviewer_emails,
                    tenant_id=tenant_id,
                )
            )
            await uow.commit()
            
        logger.info("interview_scheduled", interview_id=interview.id, tenant_id=tenant_id)
        return interview.id


class CancelInterviewUseCase:
    """Use case to cancel an interview."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        interview_id: str,
        reason: str,
        cancelled_by: str,
    ) -> None:
        """
        Cancel an existing interview.
        """
        async with self.uow as uow:
            repo = InterviewRepository(uow.session)
            interview = await repo.get(interview_id)
            
            if not interview or interview.tenant_id != tenant_id:
                raise ValueError(f"Interview {interview_id} not found")
                
            interview.cancel(reason=reason)
            
            uow.collect_event(
                InterviewCancelled(
                    interview_id=interview.id,
                    reason=reason,
                    cancelled_by=cancelled_by,
                    tenant_id=tenant_id,
                )
            )
            await uow.commit()
            
        logger.info("interview_cancelled", interview_id=interview_id, tenant_id=tenant_id)
