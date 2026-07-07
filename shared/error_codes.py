"""
Application Error Codes.

Enumerates all application-specific error codes used in Problem Details.
Consistent error codes enable client applications to handle errors gracefully.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Platform error codes."""

    # General
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INTERNAL_ERROR = "internal_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    
    # Tenant
    TENANT_NOT_FOUND = "tenant_not_found"
    TENANT_INACTIVE = "tenant_inactive"
    TENANT_QUOTA_EXCEEDED = "tenant_quota_exceeded"

    # Voice
    CALL_INITIATION_FAILED = "call_initiation_failed"
    VOICE_CLONE_CONSENT_DENIED = "voice_clone_consent_denied"
    AUDIO_PROCESSING_FAILED = "audio_processing_failed"

    # LLM
    LLM_PROVIDER_ERROR = "llm_provider_error"
    LLM_GUARDRAIL_BLOCKED = "llm_guardrail_blocked"
    LLM_TIMEOUT = "llm_timeout"

    # HR
    EMPLOYEE_NOT_FOUND = "employee_not_found"
    DEPARTMENT_NOT_FOUND = "department_not_found"
    
    # Interview
    INTERVIEW_NOT_FOUND = "interview_not_found"
    INTERVIEW_SLOT_UNAVAILABLE = "interview_slot_unavailable"
    INTERVIEW_ALREADY_CONFIRMED = "interview_already_confirmed"

    # Webhook
    INVALID_SIGNATURE = "invalid_signature"
