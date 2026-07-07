"""
Immutable audit log with HMAC hash chain tamper detection.

RULE 10: Immutable audit logs with HMAC hash chain tamper detection.
RULE 06: Audit log every data access, mutation, and AI decision.

Every audit record:
- Contains: who, what, when, where, result, tenant
- Is linked to the previous record via HMAC chain
- Cannot be modified without breaking the chain
- Is written to a separate append-only audit table

Design Pattern: Event Sourcing + HMAC Hash Chain
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from shared.metrics import AUDIT_EVENTS_TOTAL, AUDIT_TAMPER_DETECTIONS_TOTAL
from shared.settings import get_settings

logger = structlog.get_logger("audit")
settings = get_settings()


class AuditEventType(str, Enum):
    """All auditable event types in the platform."""

    # Auth events
    USER_LOGIN = "auth.user_login"
    USER_LOGOUT = "auth.user_logout"
    TOKEN_ISSUED = "auth.token_issued"
    TOKEN_REVOKED = "auth.token_revoked"
    ACCESS_DENIED = "auth.access_denied"

    # Data access
    DATA_READ = "data.read"
    DATA_CREATE = "data.create"
    DATA_UPDATE = "data.update"
    DATA_DELETE = "data.delete"
    DATA_EXPORT = "data.export"

    # Voice events
    CALL_INITIATED = "voice.call_initiated"
    CALL_COMPLETED = "voice.call_completed"
    CALL_FAILED = "voice.call_failed"
    CALL_RECORDED = "voice.call_recorded"
    CONSENT_VERIFIED = "voice.consent_verified"
    CONSENT_DENIED = "voice.consent_denied"
    AI_DISCLOSURE_DELIVERED = "voice.ai_disclosure_delivered"
    VOICE_CLONE_USED = "voice.clone_used"

    # AI events
    LLM_REQUEST = "ai.llm_request"
    LLM_RESPONSE_FILTERED = "ai.llm_response_filtered"
    GUARDRAIL_TRIGGERED = "ai.guardrail_triggered"
    PROMPT_INJECTION_DETECTED = "ai.prompt_injection_detected"

    # Tenant events
    TENANT_CREATED = "tenant.created"
    TENANT_SUSPENDED = "tenant.suspended"
    TENANT_DELETED = "tenant.deleted"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_SIGNATURE_FAILED = "webhook.signature_failed"

    # Security events
    RATE_LIMIT_EXCEEDED = "security.rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"


@dataclass
class AuditRecord:
    """A single immutable audit log entry."""

    id: str
    event_type: str
    tenant_id: str
    user_id: str | None
    resource_type: str          # e.g., "employee", "call", "document"
    resource_id: str | None     # ID of the affected resource
    action: str                 # Human-readable description
    result: str                 # "success" | "failure" | "denied"
    ip_address: str | None
    user_agent: str | None
    correlation_id: str
    metadata: dict[str, Any]
    timestamp: float
    prev_hash: str              # HMAC of previous record (hash chain)
    record_hash: str            # HMAC of this record's content


class AuditLogger:
    """
    Append-only audit logger with HMAC hash chain.

    Each record includes the hash of the previous record, creating
    a tamper-evident chain. Any modification to a record will
    invalidate all subsequent hashes.
    """

    def __init__(self) -> None:
        self._chain_key = settings.secret_key.encode() if settings.secret_key else b"audit-chain-key-change-in-prod"
        self._last_hash: dict[str, str] = {}  # tenant_id → last hash

    def _compute_hash(self, content: dict[str, Any], prev_hash: str) -> str:
        """
        Compute HMAC-SHA256 of record content + previous hash.

        Args:
            content: Record content dict (all fields except record_hash)
            prev_hash: Hash of the previous record in the chain

        Returns:
            Hex-encoded HMAC-SHA256 string
        """
        payload = json.dumps(content, sort_keys=True, default=str) + prev_hash
        return hmac.new(
            self._chain_key,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def log(
        self,
        event_type: AuditEventType,
        tenant_id: str,
        action: str,
        result: str = "success",
        resource_type: str = "",
        resource_id: str | None = None,
        user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """
        Write an audit log entry.

        The record is chained to the previous record for the same tenant.
        Emits to PostgreSQL (via async queue) and Prometheus metrics.

        Args:
            event_type: Type of auditable event
            tenant_id: Tenant context
            action: Human-readable action description
            result: Outcome ("success", "failure", "denied")
            resource_type: Type of resource affected
            resource_id: ID of affected resource
            user_id: User who performed the action (None for system actions)
            ip_address: Client IP address
            user_agent: Client user agent
            correlation_id: Request correlation ID
            metadata: Additional context (PII-safe fields only)

        Returns:
            The created AuditRecord.
        """
        if not settings.feature_audit_log_enabled:
            # Create a no-op record in development
            return AuditRecord(
                id=str(uuid.uuid4()),
                event_type=event_type.value,
                tenant_id=tenant_id,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                result=result,
                ip_address=ip_address,
                user_agent=user_agent,
                correlation_id=correlation_id,
                metadata=metadata or {},
                timestamp=time.time(),
                prev_hash="",
                record_hash="",
            )

        record_id = str(uuid.uuid4())
        timestamp = time.time()
        prev_hash = self._last_hash.get(tenant_id, "GENESIS")

        content = {
            "id": record_id,
            "event_type": event_type.value,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "result": result,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "correlation_id": correlation_id,
            "metadata": metadata or {},
            "timestamp": timestamp,
        }
        record_hash = self._compute_hash(content, prev_hash)

        record = AuditRecord(
            **content,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )

        self._last_hash[tenant_id] = record_hash

        AUDIT_EVENTS_TOTAL.labels(
            event_type=event_type.value,
            resource_type=resource_type,
        ).inc()

        logger.info(
            "audit_event",
            event_type=event_type.value,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            result=result,
            record_id=record_id,
            correlation_id=correlation_id,
        )

        await self._persist(record)
        return record

    def verify_chain(
        self, records: list[AuditRecord], tenant_id: str
    ) -> tuple[bool, int | None]:
        """
        Verify the HMAC hash chain for a sequence of records.

        Args:
            records: Ordered list of records (oldest first)
            tenant_id: Tenant whose chain to verify

        Returns:
            Tuple of (is_valid, first_broken_index).
            is_valid=True means no tampering detected.
        """
        prev_hash = "GENESIS"
        for idx, record in enumerate(records):
            content = {
                "id": record.id,
                "event_type": record.event_type,
                "tenant_id": record.tenant_id,
                "user_id": record.user_id,
                "resource_type": record.resource_type,
                "resource_id": record.resource_id,
                "action": record.action,
                "result": record.result,
                "ip_address": record.ip_address,
                "user_agent": record.user_agent,
                "correlation_id": record.correlation_id,
                "metadata": record.metadata,
                "timestamp": record.timestamp,
            }
            expected_hash = self._compute_hash(content, prev_hash)
            if not hmac.compare_digest(expected_hash, record.record_hash):
                AUDIT_TAMPER_DETECTIONS_TOTAL.inc()
                logger.error(
                    "audit_tamper_detected",
                    tenant_id=tenant_id,
                    record_id=record.id,
                    index=idx,
                    event_type=record.event_type,
                )
                return False, idx
            prev_hash = record.record_hash

        return True, None

    async def _persist(self, record: AuditRecord) -> None:
        """
        Persist audit record to PostgreSQL asynchronously.

        Uses background task to avoid blocking the request.
        """
        import asyncio
        asyncio.create_task(self._write_to_db(record))

    async def _write_to_db(self, record: AuditRecord) -> None:
        """Write audit record to the append-only audit table."""
        # DB write is injected at startup via set_db_session_factory()
        if _db_session_factory is None:
            return
        try:
            from sqlalchemy import text
            async with _db_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO audit.events (
                            id, event_type, tenant_id, user_id,
                            resource_type, resource_id, action, result,
                            ip_address, user_agent, correlation_id,
                            metadata, timestamp, prev_hash, record_hash
                        ) VALUES (
                            :id, :event_type, :tenant_id, :user_id,
                            :resource_type, :resource_id, :action, :result,
                            :ip_address, :user_agent, :correlation_id,
                            :metadata, to_timestamp(:timestamp), :prev_hash, :record_hash
                        )
                    """),
                    {
                        "id": record.id,
                        "event_type": record.event_type,
                        "tenant_id": record.tenant_id,
                        "user_id": record.user_id,
                        "resource_type": record.resource_type,
                        "resource_id": record.resource_id,
                        "action": record.action,
                        "result": record.result,
                        "ip_address": record.ip_address,
                        "user_agent": record.user_agent,
                        "correlation_id": record.correlation_id,
                        "metadata": json.dumps(record.metadata, default=str),
                        "timestamp": record.timestamp,
                        "prev_hash": record.prev_hash,
                        "record_hash": record.record_hash,
                    },
                )
                await session.commit()
        except Exception as exc:
            logger.error(
                "audit_db_write_failed",
                record_id=record.id,
                error=str(exc),
            )


# ── Module-level singleton and DB factory ─────────────────────────────────────
_db_session_factory: Any = None
_audit_logger = AuditLogger()


def set_audit_db_session_factory(factory: Any) -> None:
    """Inject the SQLAlchemy session factory for DB writes."""
    global _db_session_factory
    _db_session_factory = factory


def get_audit_logger() -> AuditLogger:
    """Return the singleton audit logger."""
    return _audit_logger
