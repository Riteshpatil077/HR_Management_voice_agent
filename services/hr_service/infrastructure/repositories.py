"""
Repositories for the HR Service.

Translates domain models to/from the database.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.hr_service.domain.models import Employee, Department
from shared.repository import BaseRepository

class EmployeeRepository(BaseRepository[Employee, str]):
    """Repository for managing Employee aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Employee, session)

    async def get_by_email(self, email: str, tenant_id: str) -> Employee | None:
        """Fetch an employee by email."""
        # Assuming classical mapping for Employee
        query = select(self.model_class).where(
            self.model_class.tenant_id == tenant_id,
            # In classical mapping, you'd navigate the ContactInfo composite
            # For simplicity, assuming a hybrid property or direct column mapping here
            self.model_class.email == email
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class DepartmentRepository(BaseRepository[Department, str]):
    """Repository for managing Departments."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Department, session)
