"""
Interviews REST API Router.

Full CRUD for managing AI interviews.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db_models import InterviewORM
from shared.unit_of_work import get_session_factory

router = APIRouter(prefix="/v1/interviews", tags=["Interviews"])

DEFAULT_TENANT = "default"


class InterviewResponse(BaseModel):
    id: str
    candidate_name: str
    role: str
    status: str
    score: float | None
    scheduled_for: str
    duration: int


class CreateInterviewRequest(BaseModel):
    candidate_id: str
    candidate_name: str
    role: str
    scheduled_for: str
    duration: int = 30


@router.get("", response_model=list[InterviewResponse])
async def list_interviews(
    status: str | None = None,
) -> list[dict]:
    """List interviews with optional filtering by status."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        query = select(InterviewORM).where(InterviewORM.tenant_id == DEFAULT_TENANT)
        if status:
            query = query.where(InterviewORM.status == status)
        query = query.order_by(InterviewORM.scheduled_for.desc())
        
        result = await session.execute(query)
        interviews = result.scalars().all()

    return [
        {
            "id": i.id,
            "candidate_name": i.candidate_name,
            "role": i.role,
            "status": i.status,
            "score": i.ai_score,
            "scheduled_for": i.scheduled_for.isoformat(),
            "duration": i.duration_minutes,
        }
        for i in interviews
    ]


@router.post("", response_model=InterviewResponse, status_code=201)
async def schedule_interview(body: CreateInterviewRequest) -> dict:
    """Schedule a new interview."""
    session_factory = get_session_factory()
    interview = InterviewORM(
        tenant_id=DEFAULT_TENANT,
        candidate_id=body.candidate_id,
        candidate_name=body.candidate_name,
        role=body.role,
        scheduled_for=datetime.fromisoformat(body.scheduled_for.replace('Z', '+00:00')),
        duration_minutes=body.duration,
        status="scheduled",
    )
    async with session_factory() as session:
        session.add(interview)
        await session.commit()
        await session.refresh(interview)

    return {
        "id": interview.id,
        "candidate_name": interview.candidate_name,
        "role": interview.role,
        "status": interview.status,
        "score": interview.ai_score,
        "scheduled_for": interview.scheduled_for.isoformat(),
        "duration": interview.duration_minutes,
    }


@router.delete("/{interview_id}", status_code=204, response_class=Response)
async def cancel_interview(interview_id: str) -> None:
    """Cancel an interview."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(InterviewORM).where(InterviewORM.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        await session.delete(interview)
        await session.commit()
