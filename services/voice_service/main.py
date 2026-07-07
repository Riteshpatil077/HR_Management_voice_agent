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
from shared.unit_of_work import create_engines, dispose_engines
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
    
    # Initialize Databases
    write_engine, read_engine = create_engines()
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

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok", "service": "voice_service"})

@app.get("/readiness", tags=["System"])
async def readiness_check() -> JSONResponse:
    """Readiness probe."""
    # In a real implementation, ping DB and Redis
    return JSONResponse({"status": "ready", "service": "voice_service"})


@app.get("/v1/analytics/dashboard", tags=["Analytics"])
async def dashboard_metrics() -> JSONResponse:
    """
    Dashboard KPI metrics endpoint consumed by the Next.js frontend.
    In production, this aggregates from the analytics_service or read replicas.
    """
    return JSONResponse({
        "total_calls_today": 1245,
        "active_calls_now": 42,
        "avg_call_duration_seconds": 185,
        "call_containment_rate": 0.87,
        "escalation_rate": 4.2,
        "lead_conversion_rate": 0.31,
        "avg_pipeline_latency_ms": 780,
        "total_cost_today_usd": 38.50,
        "calls_delta_pct": 12.5,
        "escalation_delta_pct": -1.2,
    })
