"""
Interview Service REST API Router.

Exposes endpoints for managing interviews and scheduling.
"""
from __future__ import annotations

from typing import Any
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from services.interview_service.application.use_cases import ScheduleInterviewUseCase, CancelInterviewUseCase
from shared.auth import get_current_user, TokenClaims, require_roles
from shared.idempotency import get_idempotency_key, IdempotencyStore, require_idempotency_key
from shared.unit_of_work import get_uow, UnitOfWork

router = APIRouter(prefix="/v1/interviews", tags=["Interview"])

class ScheduleInterviewRequest(BaseModel):
    job_role: str
    candidate_name: str
    candidate_email: EmailStr
    interviewer_names: list[str]
    interviewer_emails: list[EmailStr]
    start_time: datetime
    end_time: datetime

class InterviewResponse(BaseModel):
    interview_id: str
    status: str = "scheduled"


@router.post("/", response_model=InterviewResponse)
async def schedule_interview(
    req: ScheduleInterviewRequest,
    user: TokenClaims = Depends(require_roles("hr_admin", "recruiter", "system")),
    idem_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_uow),
) -> Any:
    """
    Schedule a new interview.
    Protected by Auth, Roles, and Idempotency.
    """
    idem_store = IdempotencyStore(user.tenant_id)
    
    cached_resp = await idem_store.get_stored_response(idem_key, "/v1/interviews/")
    if cached_resp:
        return cached_resp["body"]

    acquired = await idem_store.mark_in_flight(idem_key, "/v1/interviews/")
    if not acquired:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Request already in progress")

    try:
        use_case = ScheduleInterviewUseCase(uow)
        interview_id = await use_case.execute(
            tenant_id=user.tenant_id,
            job_role=req.job_role,
            candidate_name=req.candidate_name,
            candidate_email=req.candidate_email,
            interviewer_names=req.interviewer_names,
            interviewer_emails=req.interviewer_emails,
            start_time=req.start_time,
            end_time=req.end_time,
        )
        
        response_body = InterviewResponse(interview_id=interview_id).model_dump()
        
        await idem_store.store_response(
            idempotency_key=idem_key,
            path="/v1/interviews/",
            status_code=200,
            headers={},
            body=response_body,
        )
        return response_body

    finally:
        await idem_store.clear_in_flight(idem_key, "/v1/interviews/")
