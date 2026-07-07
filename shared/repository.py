"""
Generic Async Repository pattern.

Provides:
- Abstract base repository for all SQLAlchemy models
- Standard CRUD operations (get, add, update, delete)
- Cursor pagination support
- Specification pattern for complex queries

RULE 15: Zero N+1 queries. Repositories must use explicit eager loading.

Design Pattern: Repository (Evans) + Specification
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, Sequence

import structlog
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from shared.pagination import CursorPage, PageParams
from shared.settings import get_settings

logger = structlog.get_logger("repository")
settings = get_settings()

ModelType = TypeVar("ModelType")
IdType = TypeVar("IdType")


class Specification(ABC, Generic[ModelType]):
    """
    Specification pattern for building SQLAlchemy queries.

    Encapsulates query logic (filters, eager loads) so it can be
    reused across different repository methods.
    """

    @abstractmethod
    def apply(self, query: Select[tuple[ModelType]]) -> Select[tuple[ModelType]]:
        """Apply filters and eager loads to the query."""
        pass


class BaseRepository(Generic[ModelType, IdType]):
    """
    Generic async repository base class.

    All service-specific repositories should inherit from this.
    """

    def __init__(self, model_class: type[ModelType], session: AsyncSession) -> None:
        self.model_class = model_class
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get(self, id: IdType) -> ModelType | None:
        """Get a single record by primary key."""
        return await self._session.get(self.model_class, id)

    async def get_by_spec(self, spec: Specification[ModelType]) -> ModelType | None:
        """Get a single record matching a specification."""
        query = select(self.model_class)
        query = spec.apply(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list(self) -> Sequence[ModelType]:
        """List all records (use with caution on large tables)."""
        query = select(self.model_class)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def list_by_spec(
        self, spec: Specification[ModelType]
    ) -> Sequence[ModelType]:
        """List records matching a specification."""
        query = select(self.model_class)
        query = spec.apply(query)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def paginate(
        self,
        params: PageParams,
        spec: Specification[ModelType] | None = None,
        order_by: Any = None,
    ) -> CursorPage[ModelType]:
        """
        Cursor-based pagination for records.

        Args:
            params: Pagination parameters (cursor, limit, etc.)
            spec: Optional specification for filtering
            order_by: SQLAlchemy column to order by (default: model_class.id)

        Returns:
            CursorPage containing items and next_cursor.
        """
        query = select(self.model_class)
        if spec:
            query = spec.apply(query)

        # We assume id is the default ordering column if none provided
        order_col = order_by if order_by is not None else getattr(self.model_class, "id")
        
        if params.cursor:
            # Decode cursor (assuming it's the id for simplicity in this generic base)
            # A robust implementation would encode/decode tuple of (order_col_value, id)
            import base64
            try:
                decoded = base64.urlsafe_b64decode(params.cursor.encode()).decode()
                query = query.where(order_col > decoded)
            except Exception:
                pass # Invalid cursor, start from beginning

        # Fetch one extra to determine if there's a next page
        query = query.order_by(order_col.asc()).limit(params.size + 1)
        
        result = await self._session.execute(query)
        items = list(result.scalars().all())

        next_cursor = None
        if len(items) > params.size:
            items.pop() # Remove the extra item
            last_item = items[-1]
            last_val = str(getattr(last_item, order_col.name if hasattr(order_col, "name") else "id"))
            import base64
            next_cursor = base64.urlsafe_b64encode(last_val.encode()).decode()

        return CursorPage(
            items=items,
            next_cursor=next_cursor,
            size=len(items),
        )

    def add(self, entity: ModelType) -> None:
        """Add a new record to the session (requires commit)."""
        self._session.add(entity)

    async def delete(self, entity: ModelType) -> None:
        """Delete a record from the session (requires commit)."""
        await self._session.delete(entity)

    async def count(self, spec: Specification[ModelType] | None = None) -> int:
        """Count records matching a specification."""
        query = select(func.count()).select_from(self.model_class)
        if spec:
            query = spec.apply(query)
        result = await self._session.execute(query)
        count = result.scalar()
        return count if count is not None else 0
