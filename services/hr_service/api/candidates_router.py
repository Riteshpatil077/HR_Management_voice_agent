"""
Candidates REST API Router.

Full CRUD for managing candidates in the HR recruitment pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from shared.db_models import CandidateORM
from shared.unit_of_work import get_session_factory

router = APIRouter(prefix="/v1/candidates", tags=["Candidates"])

DEFAULT_TENANT = "default"


class CandidateResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    role: str
    stage: str
    ai_score: float | None
    resume_url: str | None
    notes: str | None
    last_contact_at: str
    created_at: str


class CreateCandidateRequest(BaseModel):
    name: str
    email: str
    phone: str
    role: str
    stage: str = "sourced"
    notes: str | None = None


class UpdateCandidateRequest(BaseModel):
    stage: str | None = None
    ai_score: float | None = None
    notes: str | None = None
    resume_url: str | None = None


def _to_response(c: CandidateORM) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "role": c.role,
        "stage": c.stage,
        "ai_score": c.ai_score,
        "resume_url": c.resume_url,
        "notes": c.notes,
        "last_contact_at": c.last_contact_at.isoformat() if c.last_contact_at else "",
        "created_at": c.created_at.isoformat() if c.created_at else "",
    }


@router.get("", response_model=list[CandidateResponse])
async def list_candidates(
    stage: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List candidates with optional filtering by stage or search term."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        query = select(CandidateORM).where(
            CandidateORM.tenant_id == DEFAULT_TENANT
        )
        if stage:
            query = query.where(CandidateORM.stage == stage)
        if search:
            from sqlalchemy import or_
            query = query.where(
                or_(
                    CandidateORM.name.ilike(f"%{search}%"),
                    CandidateORM.email.ilike(f"%{search}%"),
                    CandidateORM.role.ilike(f"%{search}%"),
                )
            )
        query = query.order_by(CandidateORM.last_contact_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        candidates = result.scalars().all()

    return [_to_response(c) for c in candidates]


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: str) -> dict:
    """Get a single candidate by ID."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(CandidateORM).where(
                CandidateORM.id == candidate_id,
                CandidateORM.tenant_id == DEFAULT_TENANT,
            )
        )
        candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _to_response(candidate)


@router.post("", response_model=CandidateResponse, status_code=201)
async def create_candidate(body: CreateCandidateRequest) -> dict:
    """Create a new candidate in the pipeline."""
    session_factory = get_session_factory()
    candidate = CandidateORM(
        tenant_id=DEFAULT_TENANT,
        name=body.name,
        email=body.email,
        phone=body.phone,
        role=body.role,
        stage=body.stage,
        notes=body.notes,
        last_contact_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)

    return _to_response(candidate)


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(candidate_id: str, body: UpdateCandidateRequest) -> dict:
    """Update candidate stage, score, or notes."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(CandidateORM).where(
                CandidateORM.id == candidate_id,
                CandidateORM.tenant_id == DEFAULT_TENANT,
            )
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if body.stage is not None:
            candidate.stage = body.stage
        if body.ai_score is not None:
            candidate.ai_score = body.ai_score
        if body.notes is not None:
            candidate.notes = body.notes
        if body.resume_url is not None:
            candidate.resume_url = body.resume_url
        candidate.last_contact_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(candidate)

    return _to_response(candidate)


from fastapi import Response
@router.delete("/{candidate_id}", status_code=204, response_class=Response)
async def delete_candidate(candidate_id: str) -> None:
    """Remove a candidate from the pipeline."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(CandidateORM).where(
                CandidateORM.id == candidate_id,
                CandidateORM.tenant_id == DEFAULT_TENANT,
            )
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        await session.delete(candidate)
        await session.commit()
