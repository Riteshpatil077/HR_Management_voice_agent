"""
Webhook signature verification.

RULE 14: All webhooks verified by cryptographic signature.

Verifies inbound webhooks from external providers (Exotel, Twilio, HubSpot, etc.).
Uses constant-time comparison to prevent timing attacks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import structlog
from fastapi import HTTPException, Request, status

from shared.metrics import WEBHOOK_RECEIVED_TOTAL, WEBHOOK_SIGNATURE_FAILURES_TOTAL
from shared.settings import get_settings

logger = structlog.get_logger("webhook_verify")
settings = get_settings()


async def verify_exotel_webhook(request: Request) -> bool:
    """
    Verify Exotel webhook signature.
    
    Exotel signs the POST body or query parameters using HMAC-SHA256
    with the application's API secret.
    """
    signature = request.headers.get("X-Exotel-Signature")
    if not signature:
        logger.warning("exotel_webhook_missing_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    secret = settings.exotel_webhook_hmac_secret.encode()
    if not secret:
        raise RuntimeError("Exotel webhook secret not configured")

    body = await request.body()
    expected_hash = hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_hash):
        WEBHOOK_SIGNATURE_FAILURES_TOTAL.labels(source="exotel").inc()
        logger.warning("exotel_webhook_invalid_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    WEBHOOK_RECEIVED_TOTAL.labels(source="exotel", event_type="incoming").inc()
    return True


async def verify_twilio_webhook(request: Request) -> bool:
    """
    Verify Twilio webhook signature.
    
    Twilio uses HMAC-SHA1 of the URL and POST params.
    """
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    auth_token = settings.twilio_webhook_auth_token.encode()
    url = str(request.url)
    
    # Twilio appends POST params in alphabetical order
    form_data = await request.form()
    sorted_params = "".join([f"{k}{v}" for k, v in sorted(form_data.items())])
    
    payload = (url + sorted_params).encode()
    expected_hash = base64.b64encode(hmac.new(auth_token, payload, hashlib.sha1).digest()).decode()

    if not hmac.compare_digest(signature, expected_hash):
        WEBHOOK_SIGNATURE_FAILURES_TOTAL.labels(source="twilio").inc()
        logger.warning("twilio_webhook_invalid_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    WEBHOOK_RECEIVED_TOTAL.labels(source="twilio", event_type="incoming").inc()
    return True


async def verify_meta_whatsapp_webhook(request: Request) -> bool:
    """
    Verify Meta WhatsApp webhook signature (X-Hub-Signature-256).
    """
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    signature = signature_header[7:]  # Remove 'sha256=' prefix
    secret = settings.meta_whatsapp_app_secret.encode()
    body = await request.body()
    
    expected_hash = hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected_hash):
        WEBHOOK_SIGNATURE_FAILURES_TOTAL.labels(source="whatsapp").inc()
        logger.warning("whatsapp_webhook_invalid_signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    WEBHOOK_RECEIVED_TOTAL.labels(source="whatsapp", event_type="incoming").inc()
    return True
