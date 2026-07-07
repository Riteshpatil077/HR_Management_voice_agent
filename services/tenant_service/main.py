"""Tenant Service — Stub entrypoint."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="HR Voice Agent - Tenant Service", version="3.0.0")

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "tenant_service"})

@app.get("/readiness")
async def readiness() -> JSONResponse:
    return JSONResponse({"status": "ready", "service": "tenant_service"})
