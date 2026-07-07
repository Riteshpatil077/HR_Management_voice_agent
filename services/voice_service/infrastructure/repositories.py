"""
Repositories for the Voice Service.

Translates domain models to/from the database.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.voice_service.domain.models import Call
from shared.repository import BaseRepository

# Note: In a full implementation, you would map the pure Python Domain Model `Call`
# to a SQLAlchemy ORM model (e.g., `CallORM`). For this example, we assume `Call`
# is mapped directly using SQLAlchemy's classical mapping or declarative mapping.

class CallRepository(BaseRepository[Call, str]):
    """Repository for managing Call aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Call, session)

    async def get_by_provider_call_id(self, provider_call_id: str) -> Call | None:
        """Fetch a call by its external provider ID."""
        query = select(self.model_class).where(self.model_class.provider_call_id == provider_call_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
