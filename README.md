# 🎙️ HR Voice Agent Platform

> **Enterprise-grade AI-powered HR Voice Agent** built with FastAPI, Next.js, RabbitMQ, PostgreSQL, Redis Cluster, and HashiCorp Vault.

---

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Initial Setup](#initial-setup)
- [Running the Project](#running-the-project)
- [Accessing the Services](#accessing-the-services)
- [Day-to-Day Commands](#day-to-day-commands)
- [Backend Development](#backend-development)
- [Frontend Development](#frontend-development)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                          │
│                    http://localhost:3001                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST / WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│                      FastAPI Microservices                        │
│  voice (8001) │ hr (8002) │ interview (8003) │ onboarding (8004) │
│  notification (8005) │ auth (8006) │ tenant (8007) │ analytics (8008) │
└───────────┬──────────────┬──────────────────┬────────────────────┘
            │              │                  │
     ┌──────▼──────┐ ┌────▼─────┐   ┌────────▼───────┐
     │  PostgreSQL  │ │  Redis   │   │   RabbitMQ      │
     │  :5432       │ │ Cluster  │   │   :5672         │
     └─────────────┘ │ :7001-06 │   │   UI: :15672    │
                     └──────────┘   └────────────────-─┘
```

---

## ✅ Prerequisites

Make sure you have the following installed:

| Tool | Minimum Version | Check |
|------|----------------|-------|
| Docker Desktop | 4.x | `docker --version` |
| Docker Compose | v2.x | `docker compose version` |
| Node.js | 20.x | `node --version` |
| npm | 10.x | `npm --version` |
| Python | 3.11+ | `python --version` |
| Git | any | `git --version` |

---

## 📁 Project Structure

```
hr-voice-agent/
├── services/                  # Python FastAPI microservices
│   ├── voice_service/         # Voice calls (Exotel/Twilio + LLM)
│   ├── hr_service/            # HR records management
│   ├── interview_service/     # AI-powered interview scheduling
│   ├── onboarding_service/    # Employee onboarding workflows
│   ├── auth_service/          # JWT authentication
│   ├── tenant_service/        # Multi-tenant management
│   ├── notification_service/  # Email/SMS/WhatsApp notifications
│   └── analytics_service/     # Real-time analytics & KPIs
├── shared/                    # Shared Python modules
│   ├── settings.py            # Centralised Pydantic config
│   ├── auth.py                # JWT auth middleware
│   ├── queue.py               # RabbitMQ client
│   ├── cache.py               # Redis cluster client
│   ├── unit_of_work.py        # SQLAlchemy Unit of Work
│   └── ...
├── frontend/                  # Next.js 16 + TypeScript dashboard
│   ├── src/app/               # App Router pages
│   ├── src/components/        # Shared UI components
│   └── src/lib/               # API client, hooks, utilities
├── infrastructure/            # Config for all infrastructure
│   ├── monitoring/            # Prometheus, Grafana, Loki, Tempo
│   ├── rabbitmq/              # RabbitMQ definitions + config
│   ├── redis/                 # Redis cluster config
│   └── opa/                   # Open Policy Agent Rego policies
├── scripts/                   # Init scripts (SQL, Vault)
├── docker-compose.yml         # Full local stack definition
├── pyproject.toml             # Python project & dependencies
└── .env                       # Environment variables (DO NOT commit)
```

---

## 🚀 Initial Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd hr-voice-agent
```

### 2. Configure Environment Variables

```bash
# Copy the example file and fill in your values
cp .env.example .env

# Copy the frontend example file
cp frontend/.env.local.example frontend/.env.local
```

Then open `.env` in your editor and fill in your real API keys:
- `OPENAI_API_KEY` — OpenAI key
- `DEEPGRAM_API_KEY` — Deepgram STT key
- `ELEVENLABS_API_KEY` — ElevenLabs TTS key
- `EXOTEL_API_KEY` / `EXOTEL_API_TOKEN` — Exotel telephony
- `VAULT_TOKEN=dev-root-token` — For local development

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

---

## ▶️ Running the Project

### Start Everything (Backend + Infrastructure)

```bash
# From the project root — starts all 8 microservices + databases + monitoring
docker compose up -d
```

> First run takes **5-10 minutes** because Docker downloads images and `pip install` runs inside the containers.
> Subsequent runs start in **under 30 seconds** using the image cache.

### Start the Frontend (Dashboard)

```bash
# Open a new terminal
cd frontend
npm run dev
```

The app will be available at **http://localhost:3001**

> Port 3000 is used by Grafana, so Next.js automatically uses 3001.

---

## 🌐 Accessing the Services

### Application URLs

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend Dashboard** | http://localhost:3001 | Next.js web application |

### Backend API Swagger Docs

| Service | URL |
|---------|-----|
| Voice Service | http://localhost:8001/docs |
| HR Service | http://localhost:8002/docs |
| Interview Service | http://localhost:8003/docs |
| Onboarding Service | http://localhost:8004/docs |
| Notification Service | http://localhost:8005/docs |
| Auth Service | http://localhost:8006/docs |
| Tenant Service | http://localhost:8007/docs |
| Analytics Service | http://localhost:8008/docs |

### Monitoring & Infrastructure UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | `admin` / `admin` |
| Jaeger (Tracing) | http://localhost:16686 | — |
| Prometheus | http://localhost:9090 | — |
| RabbitMQ Management | http://localhost:15672 | `hrvoice` / `hrvoice_dev_password` |
| HashiCorp Vault | http://localhost:8200 | Token: `dev-root-token` |

---

## 🛠️ Day-to-Day Commands

### Docker Compose

```bash
# Start the entire backend stack (detached)
docker compose up -d

# Stop all containers (keeps data volumes)
docker compose down

# Stop all containers AND delete all data
docker compose down -v

# View live logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f voice-service
docker compose logs -f hr-service

# Check health of all containers
docker compose ps

# Restart a specific service (e.g., after changing Python code)
docker compose restart voice-service

# Rebuild and restart a specific service (after code changes)
docker compose up -d --build voice-service

# Rebuild ALL microservices
docker compose up -d --build voice-service hr-service interview-service onboarding-service notification-service auth-service tenant-service analytics-service

# Execute a command inside a running container
docker compose exec voice-service bash
docker compose exec postgres-primary psql -U hrvoice -d hrvoice
```

### Frontend

```bash
cd frontend

# Start development server (with hot reload)
npm run dev

# Build for production
npm run build

# Start production server (after build)
npm run start

# Lint the code
npm run lint
```

### Python / Backend (from project root)

```bash
# Install Python dependencies locally for development
pip install -e ".[dev]"

# Run linter
ruff check .

# Run type checker
mypy .

# Run all tests with coverage
pytest

# Run tests for a specific service
pytest services/voice_service/tests/

# Run load tests with Locust
locust -f tests/load/locustfile.py
```

---

## 🐍 Backend Development

### Making Code Changes to a Microservice

1. Edit the Python file in `services/<service_name>/`
2. Rebuild and restart only that service:
   ```bash
   docker compose up -d --build voice-service
   ```
3. Check logs to confirm it started correctly:
   ```bash
   docker compose logs -f voice-service
   ```

### Adding a New Python Dependency

1. Add the package to `pyproject.toml` under `[project.dependencies]`
2. Rebuild the affected service(s):
   ```bash
   docker compose up -d --build voice-service
   ```

### Running Database Migrations (Alembic)

```bash
# Generate a new migration (after changing SQLAlchemy models)
docker compose exec voice-service alembic revision --autogenerate -m "add_voice_clone_table"

# Apply all pending migrations
docker compose exec voice-service alembic upgrade head

# Roll back the last migration
docker compose exec voice-service alembic downgrade -1

# View migration history
docker compose exec voice-service alembic history
```

---

## 🖥️ Frontend Development

### Making Code Changes

The frontend uses **Hot Module Replacement (HMR)** — just save your file and the browser updates instantly. No restart required.

### Adding a New npm Package

```bash
cd frontend
npm install <package-name>
```

### Calling a Backend API

The API client is in [`frontend/src/lib/api-client.ts`](frontend/src/lib/api-client.ts). The base URL is set via `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.

```typescript
import { apiClient } from "@/lib/api-client";

// GET request
const data = await apiClient.get<MyType>("/v1/voice/calls");

// POST request
const result = await apiClient.post("/v1/voice/calls", { phone_number: "..." });
```

---

## ⚙️ Environment Variables

### Critical Variables (Must be set for full functionality)

| Variable | Description | Where |
|----------|-------------|-------|
| `OPENAI_API_KEY` | OpenAI GPT-4 key | `.env` |
| `DEEPGRAM_API_KEY` | Deepgram Speech-to-Text | `.env` |
| `ELEVENLABS_API_KEY` | ElevenLabs Text-to-Speech | `.env` |
| `EXOTEL_API_KEY` | Exotel telephony (India) | `.env` |
| `VAULT_TOKEN` | `dev-root-token` for local dev | `.env` |
| `DATABASE_URL` | PostgreSQL connection string | `.env` |
| `NEXTAUTH_SECRET` | NextAuth.js session secret | `frontend/.env.local` |
| `NEXT_PUBLIC_API_URL` | Backend API URL | `frontend/.env.local` |

---

## 🔧 Troubleshooting

### Containers keep restarting

```bash
# Check what's failing
docker compose logs <service-name>
```

### Port already in use

```bash
# Find the process using the port (e.g., 8001)
netstat -ano | findstr :8001

# Kill it (replace PID with the actual number)
taskkill /PID <PID> /F
```

### Frontend shows "Another dev server is already running"

```bash
# Kill the existing Next.js process
taskkill /PID 7384 /F   # Replace with the PID shown in the error
# Then restart
npm run dev
```

### Database connection errors

```bash
# Check if PostgreSQL is healthy
docker compose ps postgres-primary

# Manually connect to the database
docker compose exec postgres-primary psql -U hrvoice -d hrvoice -c "SELECT 1"
```

### Wipe everything and start fresh

```bash
# ⚠️ This deletes ALL local data (DB, Redis, RabbitMQ volumes)
docker compose down -v
docker compose up -d
```

---

## 📄 License

Proprietary — All Rights Reserved.
