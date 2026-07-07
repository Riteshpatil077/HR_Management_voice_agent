"""
Cursor-based pagination implementation.

Provides models and dependencies for RFC-compliant cursor pagination.
Cursor pagination is required for large datasets to prevent offset scanning
performance degradation at scale.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    """Pagination parameters passed from client."""

    size: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None)


def get_page_params(
    size: int = Query(20, ge=1, le=100, description="Number of items to return"),
    cursor: str | None = Query(None, description="Cursor for the next page"),
) -> PageParams:
    """FastAPI dependency for pagination parameters."""
    return PageParams(size=size, cursor=cursor)


class CursorPage(BaseModel, Generic[T]):
    """
    Paginated response model.

    Includes the list of items and a cursor for fetching the next page.
    If next_cursor is None, there are no more pages.
    """

    items: list[T]
    size: int
    next_cursor: str | None = None
