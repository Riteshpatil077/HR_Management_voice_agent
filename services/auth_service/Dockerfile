FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi==0.111.1 "uvicorn[standard]==0.30.1" pydantic==2.8.2
COPY services/auth_service/ ./services/auth_service/
EXPOSE 8006
ENV PYTHONPATH=/app
ENV SERVICE_NAME=auth-service
ENV PORT=8006
CMD ["uvicorn", "services.auth_service.main:app", "--host", "0.0.0.0", "--port", "8006"]
