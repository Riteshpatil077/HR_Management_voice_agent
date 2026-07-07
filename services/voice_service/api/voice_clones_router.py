"""
Voice Clones REST API Router.

CRUD endpoints for managing voice clone records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db_models import VoiceCloneORM
from shared.unit_of_work import get_session_factory

router = APIRouter(prefix="/v1/voice/clones", tags=["Voice Clones"])


class VoiceCloneResponse(BaseModel):
    id: str
    voice_owner_name: str
    purpose: str
    status: str
    is_consent_verified: bool
    consented_at: str
    created_at: str


class CreateVoiceCloneRequest(BaseModel):
    voice_owner_name: str
    purpose: str
    consent_recording_url: str | None = None


def _get_tenant_id(request: Any = None) -> str:
    """Extract tenant ID from request headers. Defaults to 'default' for local dev."""
    return "default"


@router.get("", response_model=list[VoiceCloneResponse])
async def list_voice_clones() -> list[dict]:
    """List all voice clones for the current tenant."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(VoiceCloneORM).where(VoiceCloneORM.tenant_id == "default").order_by(VoiceCloneORM.created_at.desc())
        )
        clones = result.scalars().all()

    return [
        {
            "id": c.id,
            "voice_owner_name": c.voice_owner_name,
            "purpose": c.purpose,
            "status": c.status,
            "is_consent_verified": c.is_consent_verified,
            "consented_at": c.consented_at.isoformat() if c.consented_at else "",
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in clones
    ]


@router.post("", response_model=VoiceCloneResponse, status_code=201)
async def create_voice_clone(body: CreateVoiceCloneRequest) -> dict:
    """Create a new voice clone record (queued for processing by ElevenLabs)."""
    session_factory = get_session_factory()
    clone = VoiceCloneORM(
        tenant_id="default",
        voice_owner_name=body.voice_owner_name,
        purpose=body.purpose,
        consent_recording_url=body.consent_recording_url,
        status="processing",
        is_consent_verified=bool(body.consent_recording_url),
        consented_at=datetime.now(timezone.utc),
    )

    async with session_factory() as session:
        session.add(clone)
        await session.commit()
        await session.refresh(clone)

    return {
        "id": clone.id,
        "voice_owner_name": clone.voice_owner_name,
        "purpose": clone.purpose,
        "status": clone.status,
        "is_consent_verified": clone.is_consent_verified,
        "consented_at": clone.consented_at.isoformat() if clone.consented_at else "",
        "created_at": clone.created_at.isoformat() if clone.created_at else "",
    }


from fastapi import Response
@router.delete("/{clone_id}", status_code=204, response_class=Response)
async def delete_voice_clone(clone_id: str) -> None:
    """Revoke and delete a voice clone."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(VoiceCloneORM).where(VoiceCloneORM.id == clone_id)
        )
        clone = result.scalar_one_or_none()
        if not clone:
            raise HTTPException(status_code=404, detail="Voice clone not found")
        await session.delete(clone)
        await session.commit()
