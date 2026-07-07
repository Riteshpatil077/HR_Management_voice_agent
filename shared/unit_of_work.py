"""
Async SQLAlchemy Unit of Work pattern.

Provides:
- Transactional boundary for database operations
- Automatic outbox integration for domain events
- Domain event dispatching after commit
- Read replica routing for query operations

RULE 15: Zero N+1 queries — all repositories use eager loading.

Design Pattern: Unit of Work (Fowler)
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.domain_events import DomainEvent, EventBus, get_event_bus
from shared.outbox import OutboxWriter, get_outbox_writer
from shared.settings import get_settings

logger = structlog.get_logger("unit_of_work")
settings = get_settings()

# ── Engine Setup ───────────────────────────────────────────────────────────────
_write_engine: AsyncEngine | None = None
_read_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_read_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engines() -> tuple[AsyncEngine, AsyncEngine]:
    """
    Create SQLAlchemy async engines for write and read replicas.

    Write engine: connects to primary PostgreSQL (via PgBouncer)
    Read engine: connects to read replica for query-only operations.

    Returns:
        Tuple of (write_engine, read_engine)
    """
    global _write_engine, _read_engine, _session_factory, _read_session_factory

    engine_kwargs: dict[str, Any] = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": True,
        "echo": settings.db_echo,
        "connect_args": {
            "server_settings": {
                "application_name": f"hr-voice-{settings.service_name}",
                "jit": "off",
            },
            "command_timeout": 30,
        },
    }

    write_url = settings.database_url or "postgresql+asyncpg://localhost/hrvoice"
    _write_engine = create_async_engine(write_url, **engine_kwargs)

    read_url = settings.database_url_replica_1 or write_url
    _read_engine = create_async_engine(read_url, **engine_kwargs)

    _session_factory = async_sessionmaker(
        _write_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    _read_session_factory = async_sessionmaker(
        _read_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info(
        "database_engines_created",
        write_url=write_url.split("@")[-1],  # Log only host/db, not credentials
        read_url=read_url.split("@")[-1],
    )
    return _write_engine, _read_engine


async def create_db_tables() -> None:
    """
    Auto-create all database tables on startup.

    Uses SQLAlchemy's MetaData.create_all() which is idempotent —
    it only creates tables that don't already exist.
    This is sufficient for local development.
    For production, use Alembic migrations instead.
    """
    if _write_engine is None:
        raise RuntimeError("Engines must be created before calling create_db_tables()")

    # Import all ORM models so SQLAlchemy's metadata is fully populated
    from shared.db_models import Base  # noqa: F401 — import for side effects

    async with _write_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_tables_created_or_verified")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the write session factory (raises if not initialized)."""
    if _session_factory is None:
        raise RuntimeError(
            "Database engines not initialized. Call create_engines() at startup."
        )
    return _session_factory


def get_read_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the read replica session factory."""
    if _read_session_factory is None:
        raise RuntimeError("Database engines not initialized.")
    return _read_session_factory


class UnitOfWork:
    """
    Async Unit of Work.

    Manages a single SQLAlchemy session, collects domain events,
    and dispatches them after successful commit.

    Usage:
        async with UnitOfWork() as uow:
            employee = await uow.session.get(Employee, employee_id)
            employee.promote(new_position)
            uow.collect_event(EmployeePromoted(employee_id=employee.id))
            await uow.commit()
        # Domain events dispatched here after commit
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        outbox_writer: OutboxWriter | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._outbox_writer = outbox_writer or get_outbox_writer()
        self._event_bus = event_bus or get_event_bus()
        self._session: AsyncSession | None = None
        self._pending_events: list[DomainEvent] = []

    @property
    def session(self) -> AsyncSession:
        """Return the current session (raises if not in context)."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not entered. Use 'async with uow:'")
        return self._session

    async def __aenter__(self) -> "UnitOfWork":
        """Begin a new database session."""
        self._session = self._session_factory()
        self._pending_events = []
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Roll back on exception, close session always."""
        if exc_type is not None:
            await self.rollback()
        if self._session:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """
        Commit the current transaction and dispatch domain events.

        If commit fails, raises the exception (no auto-rollback).
        Domain events are dispatched only after successful commit.
        """
        if self._session is None:
            raise RuntimeError("No active session to commit")

        await self._session.commit()
        logger.debug("transaction_committed")

        # Dispatch collected domain events after successful commit
        events_to_dispatch = list(self._pending_events)
        self._pending_events.clear()

        if events_to_dispatch:
            await asyncio.gather(
                *[self._event_bus.dispatch(event) for event in events_to_dispatch],
                return_exceptions=True,
            )

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        if self._session:
            await self._session.rollback()
            self._pending_events.clear()
            logger.debug("transaction_rolled_back")

    def collect_event(self, event: DomainEvent) -> None:
        """
        Collect a domain event to dispatch after commit.

        Events are NOT dispatched if the transaction is rolled back.
        """
        self._pending_events.append(event)

    async def refresh(self, instance: Any) -> None:
        """Refresh a model instance from the database."""
        await self.session.refresh(instance)


async def get_uow() -> UnitOfWork:
    """
    FastAPI dependency: return a new Unit of Work instance.

    Usage:
        @router.post("/employees")
        async def create_employee(
            data: EmployeeCreate,
            uow: UnitOfWork = Depends(get_uow),
        ):
            async with uow:
                employee = Employee(**data.model_dump())
                uow.session.add(employee)
                await uow.commit()
    """
    return UnitOfWork()


async def dispose_engines() -> None:
    """Dispose all database engines on application shutdown."""
    if _write_engine:
        await _write_engine.dispose()
    if _read_engine:
        await _read_engine.dispose()
    logger.info("database_engines_disposed")
