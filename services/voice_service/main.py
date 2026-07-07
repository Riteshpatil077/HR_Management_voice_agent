"""
Voice Service Entrypoint (FastAPI).

Assembles the routers, middleware, and startup events.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

from services.voice_service.api.router import router as voice_router
from services.voice_service.api.websockets import router as ws_router
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

logger = structlog.get_logger("voice_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for the Voice Service."""
    logger.info("voice_service_starting", version=settings.app_version)
    
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
    
    # Start RabbitMQ Consumers for this service
    from shared.queue import QueueName
    from services.voice_service.workers.call_events import handle_call_analytics
    
    await mq.consume(
        queue=QueueName.CALL_ANALYTICS,
        handler=handle_call_analytics,
        concurrency=10,
    )
    
    yield
    
    logger.info("voice_service_shutting_down")
    await outbox_worker.stop()
    await stop_cost_flush_worker()
    await mq.close()
    await dispose_engines()
    await close_redis()

app = FastAPI(
    title="HR Voice Agent - Voice Service",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

# Exception handlers
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── CORS — allow the Next.js frontend origin ─────────────────────────────────
# CORS_ORIGINS env var is comma-separated and parsed into list[str] by Pydantic.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Request-ID"],
)

# Middleware (Order is innermost to outermost conceptually, but FastAPI adds them in reverse order)
# Actually starlette applies them in the order added.
app.add_middleware(MetricsMiddleware, service_name="voice_service")
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(CorrelationIDMiddleware)

# Routers
app.include_router(voice_router)
app.include_router(ws_router)

from services.voice_service.api.voice_clones_router import router as clones_router
app.include_router(clones_router)

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok", "service": "voice_service"})

@app.get("/readiness", tags=["System"])
async def readiness_check() -> JSONResponse:
    """Readiness probe — pings DB and returns status."""
    from shared.unit_of_work import get_session_factory
    from sqlalchemy import text
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "degraded"
    return JSONResponse({"status": "ready" if db_status == "ok" else "degraded", "service": "voice_service", "db": db_status})


@app.get("/v1/analytics/dashboard", tags=["Analytics"])
async def dashboard_metrics() -> JSONResponse:
    """
    Dashboard KPI metrics — aggregated from the calls table in real-time.
    """
    from datetime import date
    from sqlalchemy import func, select, text
    from shared.db_models import CallORM
    from shared.unit_of_work import get_session_factory

    session_factory = get_session_factory()
    today = date.today()

    try:
        async with session_factory() as session:
            # Total calls today
            total_today = await session.scalar(
                select(func.count(CallORM.id)).where(
                    func.date(CallORM.created_at) == today
                )
            ) or 0

            # Active calls right now
            active_now = await session.scalar(
                select(func.count(CallORM.id)).where(
                    CallORM.state == "in_progress"
                )
            ) or 0

            # Average duration of completed calls today
            avg_duration = await session.scalar(
                select(func.avg(CallORM.duration_seconds)).where(
                    func.date(CallORM.created_at) == today,
                    CallORM.state == "completed",
                )
            ) or 0

            # Failed/escalated calls for escalation rate
            failed = await session.scalar(
                select(func.count(CallORM.id)).where(
                    func.date(CallORM.created_at) == today,
                    CallORM.state == "failed",
                )
            ) or 0

            escalation_rate = round((failed / total_today * 100) if total_today > 0 else 0.0, 1)

        return JSONResponse({
            "total_calls_today": total_today,
            "active_calls_now": active_now,
            "avg_call_duration_seconds": round(float(avg_duration)),
            "call_containment_rate": round(1.0 - (escalation_rate / 100), 2),
            "escalation_rate": escalation_rate,
            "lead_conversion_rate": 0.0,   # Requires CRM integration
            "avg_pipeline_latency_ms": 0,   # Requires OTEL aggregation
            "total_cost_today_usd": 0.0,    # Requires cost_tracker aggregation
            "calls_delta_pct": 0.0,
            "escalation_delta_pct": 0.0,
        })
    except Exception as exc:
        logger.error("dashboard_metrics_failed", error=str(exc))
        return JSONResponse({"error": "metrics unavailable"}, status_code=503)
