"""
Voice Service REST API Router.

Exposes endpoints for initiating calls and receiving provider webhooks.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from pydantic import BaseModel

from services.voice_service.application.use_cases import InitiateCallUseCase
from shared.auth import get_current_user, TokenClaims, require_roles
from shared.idempotency import get_idempotency_key, IdempotencyStore, require_idempotency_key
from shared.unit_of_work import get_uow, UnitOfWork
from shared.webhook_verify import verify_exotel_webhook

router = APIRouter(prefix="/v1/voice", tags=["Voice"])

class InitiateCallRequest(BaseModel):
    phone_number: str
    participant_role: str
    prompt_name: str
    prompt_version: str = "v1"
    variables: dict[str, str] = {}
    participant_id: str | None = None

class CallResponse(BaseModel):
    call_id: str
    status: str = "initiated"


@router.post("/calls", response_model=CallResponse)
async def initiate_call(
    req: InitiateCallRequest,
    user: TokenClaims = Depends(require_roles("hr_admin", "recruiter", "system")),
    idem_key: str = Depends(require_idempotency_key),
    uow: UnitOfWork = Depends(get_uow),
) -> Any:
    """
    Initiate an outbound voice call.
    Protected by Auth, Roles, and Idempotency.
    """
    idem_store = IdempotencyStore(user.tenant_id)
    
    # 1. Check idempotency cache
    cached_resp = await idem_store.get_stored_response(idem_key, "/v1/voice/calls")
    if cached_resp:
        return cached_resp["body"]

    # 2. Prevent concurrent requests with same key
    acquired = await idem_store.mark_in_flight(idem_key, "/v1/voice/calls")
    if not acquired:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Request already in progress")

    try:
        # 3. Execute Use Case
        use_case = InitiateCallUseCase(uow)
        call_id = await use_case.execute(
            tenant_id=user.tenant_id,
            phone_number=req.phone_number,
            participant_role=req.participant_role,
            prompt_name=req.prompt_name,
            prompt_version=req.prompt_version,
            variables=req.variables,
            participant_id=req.participant_id,
        )
        
        response_body = CallResponse(call_id=call_id).model_dump()
        
        # 4. Store successful response
        await idem_store.store_response(
            idempotency_key=idem_key,
            path="/v1/voice/calls",
            status_code=200,
            headers={},
            body=response_body,
        )
        return response_body

    finally:
        await idem_store.clear_in_flight(idem_key, "/v1/voice/calls")


@router.post("/webhooks/exotel/{tenant_id}")
async def exotel_webhook(
    tenant_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    is_valid: bool = Depends(verify_exotel_webhook),
) -> dict[str, str]:
    """
    Receive Exotel call state webhook.
    Verifies HMAC signature, extracts payload, and queues for async processing.
    """
    payload = dict(await request.form())
    
    # In a real app, publish to RabbitMQ or use a background task
    from shared.queue import publish_message, QueueMessage, QueueName
    
    msg = QueueMessage(
        queue=QueueName.CALL_ANALYTICS, # Example queue
        payload={"provider": "exotel", "event": payload},
        tenant_id=tenant_id,
    )
    
    background_tasks.add_task(publish_message, msg)
    
    return {"status": "accepted"}
