"""
RabbitMQ workers for Voice Service.

Processes async events from the queue (e.g. Call Analytics, Outbox Relay).
"""
from __future__ import annotations

import structlog
from typing import Any

from shared.domain_events import CallCompleted
from shared.integration.factory import IntegrationFactory
from shared.integration.base import IntegrationRequest
from shared.integration.adapters.crm.base import CRMRequestData

logger = structlog.get_logger("voice_service.workers")

async def handle_call_analytics(payload: dict[str, Any]) -> None:
    """
    Process call analytics events from the queue.
    """
    event = payload.get("event", {})
    provider = payload.get("provider")
    tenant_id = payload.get("_meta", {}).get("tenant_id")
    
    logger.info("processing_call_analytics", provider=provider, tenant_id=tenant_id)
    # E.g., Parse Exotel webhook event, calculate duration, update database


async def handle_call_completed(payload: dict[str, Any]) -> None:
    """
    Process the CallCompleted domain event (via outbox relay -> rabbitmq).
    Syncs the completed call to the CRM.
    """
    event = CallCompleted(**payload)
    
    logger.info("processing_call_completed", call_id=event.call_id)
    
    crm = IntegrationFactory.get_crm_adapter(event.tenant_id, preferred_provider="hubspot")
    
    req = IntegrationRequest(
        provider=crm.provider_name,
        operation="log_call",
        payload=CRMRequestData(
            action="log_call",
            entity_type="Contact",
            data={
                "call_id": event.call_id,
                "duration": event.duration_seconds,
                "outcome": event.outcome,
                "transcript_url": event.transcript_url,
            }
        ),
        tenant_id=event.tenant_id,
        correlation_id=event.correlation_id,
    )
    
    resp = await crm.sync(req)
    if resp.success:
        logger.info("crm_sync_successful", call_id=event.call_id)
    else:
        logger.error("crm_sync_failed", call_id=event.call_id, error=resp.provider_raw_response)
