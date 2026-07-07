"""
Repositories for the Onboarding Service.

Translates domain models to/from the database.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.onboarding_service.domain.models import OnboardingPlan
from shared.repository import BaseRepository

class OnboardingRepository(BaseRepository[OnboardingPlan, str]):
    """Repository for managing OnboardingPlan aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(OnboardingPlan, session)
