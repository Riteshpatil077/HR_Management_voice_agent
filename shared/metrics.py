"""
Prometheus metrics registry.

All Prometheus metrics for the platform are defined here.
Services import metrics from this module — never define metrics locally.
This prevents duplicate metric registration and ensures naming consistency.

Naming convention: {namespace}_{subsystem}_{metric}_{unit}
"""
from __future__ import annotations

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Summary,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# ── HTTP API Metrics ──────────────────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "hr_voice_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code", "service"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "hr_voice_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "service"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5],
)

HTTP_REQUEST_SIZE_BYTES = Summary(
    "hr_voice_http_request_size_bytes",
    "HTTP request payload size",
    ["method", "endpoint"],
)

HTTP_RESPONSE_SIZE_BYTES = Summary(
    "hr_voice_http_response_size_bytes",
    "HTTP response payload size",
    ["method", "endpoint"],
)

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "hr_voice_http_requests_in_flight",
    "Current HTTP requests being processed",
    ["service"],
)

# ── Voice Pipeline Metrics ─────────────────────────────────────────────────────
VOICE_CALLS_TOTAL = Counter(
    "hr_voice_calls_total",
    "Total voice calls initiated",
    ["tenant_id", "status", "telephony_provider"],
)

VOICE_CALL_DURATION_SECONDS = Histogram(
    "hr_voice_call_duration_seconds",
    "Voice call duration in seconds",
    ["tenant_id", "outcome"],
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
)

VOICE_PIPELINE_LATENCY_SECONDS = Histogram(
    "hr_voice_pipeline_latency_seconds",
    "End-to-end voice pipeline latency (STT + LLM + TTS)",
    ["tenant_id", "intent"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5, 2.0, 5.0],
)

VOICE_STT_LATENCY_SECONDS = Histogram(
    "hr_voice_stt_latency_seconds",
    "STT transcription latency",
    ["provider"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 2.0],
)

VOICE_TTS_LATENCY_SECONDS = Histogram(
    "hr_voice_tts_latency_seconds",
    "TTS synthesis latency",
    ["provider"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 2.0],
)

VOICE_CONCURRENT_CALLS = Gauge(
    "hr_voice_concurrent_calls",
    "Number of currently active voice calls",
    ["tenant_id"],
)

VOICE_CONSENT_CHECKS_TOTAL = Counter(
    "hr_voice_consent_checks_total",
    "Voice clone consent verification outcomes",
    ["tenant_id", "result"],
)

# ── LLM Metrics ───────────────────────────────────────────────────────────────
LLM_REQUESTS_TOTAL = Counter(
    "hr_voice_llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "intent", "status"],
)

LLM_LATENCY_SECONDS = Histogram(
    "hr_voice_llm_latency_seconds",
    "LLM response latency",
    ["provider", "model"],
    buckets=[0.1, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
)

LLM_TOKENS_TOTAL = Counter(
    "hr_voice_llm_tokens_total",
    "Total LLM tokens consumed",
    ["provider", "model", "token_type"],  # token_type: input|output
)

LLM_COST_USD_TOTAL = Counter(
    "hr_voice_llm_cost_usd_total",
    "Total LLM cost in USD",
    ["provider", "model", "tenant_id"],
)

LLM_FALLBACK_TOTAL = Counter(
    "hr_voice_llm_fallback_total",
    "Total LLM provider fallback events",
    ["from_provider", "to_provider", "reason"],
)

LLM_GUARDRAIL_REJECTIONS_TOTAL = Counter(
    "hr_voice_llm_guardrail_rejections_total",
    "Total LLM responses rejected by guardrails",
    ["rule", "tenant_id"],
)

# ── Integration Layer Metrics ─────────────────────────────────────────────────
INTEGRATION_REQUESTS = Counter(
    "hr_voice_integration_requests_total",
    "Total external integration requests",
    ["provider", "operation", "status"],
)

INTEGRATION_LATENCY = Histogram(
    "hr_voice_integration_latency_milliseconds",
    "External integration call latency in milliseconds",
    ["provider", "operation"],
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000, 5000],
)

INTEGRATION_ERRORS = Counter(
    "hr_voice_integration_errors_total",
    "Total external integration errors",
    ["provider", "operation", "error_type"],
)

INTEGRATION_CIRCUIT_BREAKER_STATE = Gauge(
    "hr_voice_circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=half_open, 2=open",
    ["provider"],
)

INTEGRATION_CIRCUIT_BREAKER_TRIPS = Counter(
    "hr_voice_circuit_breaker_trips_total",
    "Total circuit breaker trip events",
    ["provider"],
)

# ── Database Metrics ───────────────────────────────────────────────────────────
DB_QUERY_DURATION_SECONDS = Histogram(
    "hr_voice_db_query_duration_seconds",
    "Database query execution time",
    ["operation", "table", "tenant_id"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

DB_POOL_SIZE = Gauge(
    "hr_voice_db_pool_size",
    "Database connection pool size",
    ["pool_type"],
)

DB_POOL_CHECKED_OUT = Gauge(
    "hr_voice_db_pool_checked_out",
    "Database connections currently checked out",
    [],
)

# ── Cache Metrics ──────────────────────────────────────────────────────────────
CACHE_HITS_TOTAL = Counter(
    "hr_voice_cache_hits_total",
    "Total cache hits",
    ["namespace", "operation"],
)

CACHE_MISSES_TOTAL = Counter(
    "hr_voice_cache_misses_total",
    "Total cache misses",
    ["namespace", "operation"],
)

CACHE_ERRORS_TOTAL = Counter(
    "hr_voice_cache_errors_total",
    "Total cache errors",
    ["namespace", "error_type"],
)

CACHE_OPERATION_DURATION_SECONDS = Histogram(
    "hr_voice_cache_operation_duration_seconds",
    "Cache operation duration",
    ["operation"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)

# ── Queue Metrics ──────────────────────────────────────────────────────────────
QUEUE_MESSAGES_PUBLISHED_TOTAL = Counter(
    "hr_voice_queue_messages_published_total",
    "Total messages published to queue",
    ["queue_name", "exchange"],
)

QUEUE_MESSAGES_CONSUMED_TOTAL = Counter(
    "hr_voice_queue_messages_consumed_total",
    "Total messages consumed from queue",
    ["queue_name", "status"],
)

QUEUE_MESSAGE_PROCESSING_SECONDS = Histogram(
    "hr_voice_queue_message_processing_seconds",
    "Message processing duration",
    ["queue_name"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

QUEUE_DLQ_MESSAGES_TOTAL = Counter(
    "hr_voice_queue_dlq_messages_total",
    "Total messages sent to dead letter queue",
    ["queue_name", "reason"],
)

# ── Auth Metrics ───────────────────────────────────────────────────────────────
AUTH_TOKEN_ISSUED_TOTAL = Counter(
    "hr_voice_auth_token_issued_total",
    "Total JWT tokens issued",
    ["token_type", "tenant_id"],
)

AUTH_TOKEN_REJECTED_TOTAL = Counter(
    "hr_voice_auth_token_rejected_total",
    "Total JWT token validation failures",
    ["reason"],
)

AUTH_OPA_DECISIONS_TOTAL = Counter(
    "hr_voice_auth_opa_decisions_total",
    "Total OPA policy decisions",
    ["policy", "decision"],
)

AUTH_OPA_LATENCY_SECONDS = Histogram(
    "hr_voice_auth_opa_latency_seconds",
    "OPA policy evaluation latency",
    ["policy"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
)

# ── Tenant Metrics ─────────────────────────────────────────────────────────────
TENANT_ACTIVE_TOTAL = Gauge(
    "hr_voice_tenant_active_total",
    "Number of active tenants",
    [],
)

TENANT_API_REQUESTS_TOTAL = Counter(
    "hr_voice_tenant_api_requests_total",
    "API requests per tenant",
    ["tenant_id", "service"],
)

# ── Audit Metrics ──────────────────────────────────────────────────────────────
AUDIT_EVENTS_TOTAL = Counter(
    "hr_voice_audit_events_total",
    "Total audit log events recorded",
    ["event_type", "resource_type"],
)

AUDIT_TAMPER_DETECTIONS_TOTAL = Counter(
    "hr_voice_audit_tamper_detections_total",
    "Total audit log tamper detection events",
    [],
)

# ── Cost Tracking Metrics ──────────────────────────────────────────────────────
COST_USD_TOTAL = Counter(
    "hr_voice_cost_usd_total",
    "Total cost in USD",
    ["provider", "operation_type", "tenant_id"],
)

COST_S3_BYTES_STORED = Gauge(
    "hr_voice_cost_s3_bytes_stored",
    "Bytes stored in S3 per tenant",
    ["tenant_id", "bucket"],
)

# ── Webhook Metrics ────────────────────────────────────────────────────────────
WEBHOOK_RECEIVED_TOTAL = Counter(
    "hr_voice_webhook_received_total",
    "Total webhooks received",
    ["source", "event_type"],
)

WEBHOOK_SIGNATURE_FAILURES_TOTAL = Counter(
    "hr_voice_webhook_signature_failures_total",
    "Total webhook signature verification failures",
    ["source"],
)
