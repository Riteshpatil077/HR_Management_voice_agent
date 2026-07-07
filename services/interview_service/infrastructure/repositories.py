"""
Repositories for the Interview Service.

Translates domain models to/from the database.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.interview_service.domain.models import Interview
from shared.repository import BaseRepository

class InterviewRepository(BaseRepository[Interview, str]):
    """Repository for managing Interview aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Interview, session)

    # Add custom queries for interviews (e.g. by candidate, by date range)
