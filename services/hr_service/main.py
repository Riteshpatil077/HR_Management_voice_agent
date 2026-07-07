"""
HR Service Entrypoint (FastAPI).

Assembles the routers, middleware, and startup events.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import structlog

from services.hr_service.api.router import router as hr_router
from shared.middleware import (
    CorrelationIDMiddleware,
    MetricsMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from shared.problem_details import unhandled_exception_handler
from shared.settings import get_settings
from shared.unit_of_work import create_engines, create_db_tables, dispose_engines
from shared.cache import close_redis
from shared.queue import get_queue_client
from shared.outbox import OutboxRelayWorker
from shared.audit import set_audit_db_session_factory
from shared.cost_tracker import start_cost_flush_worker, stop_cost_flush_worker

logger = structlog.get_logger("hr_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the HR Service."""
    logger.info("hr_service_starting", version=settings.app_version)
    
    # Initialize Databases & auto-create tables
    write_engine, read_engine = create_engines()
    await create_db_tables()
    from shared.unit_of_work import get_session_factory
    session_factory = get_session_factory()
    
    # Initialize background infrastructure
    set_audit_db_session_factory(session_factory)
    await start_cost_flush_worker(session_factory)
    
    # Start Outbox Relay Worker
    outbox_worker = OutboxRelayWorker(session_factory)
    await outbox_worker.start()
    
    # Initialize RabbitMQ
    mq = await get_queue_client()
    
    yield
    
    logger.info("hr_service_shutting_down")
    await outbox_worker.stop()
    await stop_cost_flush_worker()
    await mq.close()
    await dispose_engines()
    await close_redis()

app = FastAPI(
    title="HR Voice Agent - HR Service",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

# Exception handlers
app.add_exception_handler(Exception, unhandled_exception_handler)

# Middleware
app.add_middleware(MetricsMiddleware, service_name="hr_service")
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(CorrelationIDMiddleware)

# Routers
app.include_router(hr_router)

from services.hr_service.api.candidates_router import router as candidates_router
app.include_router(candidates_router)

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok", "service": "hr_service"})

@app.get("/readiness", tags=["System"])
async def readiness_check() -> JSONResponse:
    """Readiness probe."""
    return JSONResponse({"status": "ready", "service": "hr_service"})
