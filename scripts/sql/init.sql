-- =============================================================================
-- HR Voice Agent Platform — PostgreSQL Initialisation Script
-- Runs once on first container start via docker-entrypoint-initdb.d
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ─── Tenants ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    name          TEXT        NOT NULL,
    slug          TEXT        NOT NULL UNIQUE,
    plan          TEXT        NOT NULL DEFAULT 'starter',
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Employees ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS employees (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    first_name    TEXT        NOT NULL,
    last_name     TEXT        NOT NULL,
    email         TEXT        NOT NULL,
    department    TEXT,
    role          TEXT,
    status        TEXT        NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX IF NOT EXISTS idx_employees_tenant ON employees(tenant_id);

-- ─── Interviews ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interviews (
    id                UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id         UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    candidate_name    TEXT        NOT NULL,
    candidate_email   TEXT        NOT NULL,
    role              TEXT        NOT NULL,
    scheduled_at      TIMESTAMPTZ,
    status            TEXT        NOT NULL DEFAULT 'scheduled',
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_interviews_tenant ON interviews(tenant_id);

-- ─── Onboarding Plans ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_plans (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id     UUID        NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    department_id   TEXT,
    status          TEXT        NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_onboarding_tenant ON onboarding_plans(tenant_id);

-- ─── Onboarding Tasks ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_tasks (
    id          UUID    PRIMARY KEY DEFAULT uuid_generate_v4(),
    plan_id     UUID    NOT NULL REFERENCES onboarding_plans(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    description TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending'
);

-- ─── Call Records ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS call_records (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    call_id         TEXT        NOT NULL UNIQUE,
    phone_number    TEXT        NOT NULL,
    direction       TEXT        NOT NULL DEFAULT 'outbound',
    status          TEXT        NOT NULL DEFAULT 'initiated',
    duration_sec    INTEGER,
    llm_cost_usd    NUMERIC(10,4),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_call_records_tenant ON call_records(tenant_id);

-- ─── Audit Log ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     UUID,
    user_id       TEXT,
    action        TEXT        NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    ip_address    TEXT,
    user_agent    TEXT,
    metadata      JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- ─── Outbox Messages (Transactional Outbox Pattern) ──────────────────────────
CREATE TABLE IF NOT EXISTS outbox_messages (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID,
    aggregate_type  TEXT        NOT NULL,
    aggregate_id    TEXT        NOT NULL,
    event_type      TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
    retry_count     INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_messages(status, created_at);

-- ─── Cost Tracking ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS call_analytics (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID,
    call_id         TEXT,
    provider        TEXT,
    model           TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    cost_usd        NUMERIC(10,6),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Idempotency Keys ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS idempotency_records (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       TEXT        NOT NULL,
    idempotency_key TEXT        NOT NULL,
    path            TEXT        NOT NULL,
    status_code     INTEGER,
    response_body   JSONB,
    in_flight       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, idempotency_key, path)
);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_records(expires_at);

-- ─── Seed Demo Tenant ─────────────────────────────────────────────────────────
INSERT INTO tenants (id, name, slug, plan)
VALUES ('00000000-0000-0000-0000-000000000001', 'Demo Corp', 'demo', 'enterprise')
ON CONFLICT (slug) DO NOTHING;
