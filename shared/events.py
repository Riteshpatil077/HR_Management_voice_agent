"""
System events and schemas.

Defines standard schemas for events that cross service boundaries.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

class WebhookEvent(BaseModel):
    """Normalized webhook event from an external provider."""
    
    provider: str
    event_type: str
    raw_payload: dict[str, Any]
    tenant_id: str | None = None
    processed: bool = False

class CallAnalyticsEvent(BaseModel):
    """Event sent to the analytics service when a call completes."""
    
    call_id: str
    tenant_id: str
    duration_seconds: int
    cost_usd: float
    stt_provider: str
    tts_provider: str
    llm_provider: str
    intent_detected: str
    outcome: str
    transcription: str
