"""Auth Service — Stub entrypoint."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="HR Voice Agent - Auth Service", version="3.0.0")

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "auth_service"})

@app.get("/readiness")
async def readiness() -> JSONResponse:
    return JSONResponse({"status": "ready", "service": "auth_service"})
