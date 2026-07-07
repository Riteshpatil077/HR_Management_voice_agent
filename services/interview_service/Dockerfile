# ─────────────────────────────────────────────────────────────────────────────
# Interview Service Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        fastapi==0.111.1 "uvicorn[standard]==0.30.1" python-multipart==0.0.9 \
        "sqlalchemy[asyncio]==2.0.31" asyncpg==0.29.0 greenlet==3.0.3 \
        "redis[hiredis]==5.0.7" pydantic==2.8.2 pydantic-settings==2.4.0 \
        aio-pika==9.4.3 aiormq==6.8.1 "httpx[http2]==0.27.0" \
        "python-jose[cryptography]==3.3.0" "passlib[bcrypt]==1.7.4" cryptography==43.0.0 \
        structlog==24.4.0 "opentelemetry-sdk==1.25.0" "opentelemetry-api==1.25.0" \
        "opentelemetry-instrumentation-fastapi==0.46b0" prometheus-client==0.20.0 \
        hvac==2.3.0 tenacity==8.5.0 ujson==5.10.0

COPY shared/ ./shared/
COPY services/interview_service/ ./services/interview_service/

EXPOSE 8003
ENV PYTHONPATH=/app
ENV SERVICE_NAME=interview-service
ENV PORT=8003

CMD ["uvicorn", "services.interview_service.main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
