"""
SQLAlchemy ORM Table Definitions.

These are the actual database table mappings. The domain models (in each service's
domain/models.py) are pure Python dataclasses following DDD — they have no SQLAlchemy
dependency. These ORM classes are the persistence layer bridge.

Design Pattern: Repository (Evans) — domain model ↔ ORM model mapping.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ── Calls ─────────────────────────────────────────────────────────────────────

class CallORM(Base):
    """Persists a Call aggregate to the `calls` table."""

    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="initiated")
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    participant_role: Mapped[str] = mapped_column(String(50), nullable=False)
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prompt_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Call id={self.id} state={self.state}>"


# ── Candidates ────────────────────────────────────────────────────────────────

class CandidateORM(Base):
    """Persists a Candidate record to the `candidates` table."""

    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str] = mapped_column(
        String(50), nullable=False, default="sourced"
    )  # sourced | screening | interviewed | offered | onboarding | rejected
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resume_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_contact_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} name={self.name} stage={self.stage}>"


# ── Interviews ────────────────────────────────────────────────────────────────

class InterviewORM(Base):
    """Persists an AI Interview record to the `interviews` table."""

    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="scheduled"
    )  # scheduled | in_progress | completed | cancelled
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<Interview id={self.id} candidate={self.candidate_name} status={self.status}>"


# ── Voice Clones ───────────────────────────────────────────────────────────────

class VoiceCloneORM(Base):
    """Persists a Voice Clone record to the `voice_clones` table."""

    __tablename__ = "voice_clones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    voice_owner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processing"
    )  # processing | active | inactive | revoked
    provider_voice_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    consent_recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_consent_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<VoiceClone id={self.id} owner={self.voice_owner_name} status={self.status}>"
