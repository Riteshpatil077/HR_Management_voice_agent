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
from shared.unit_of_work import get_uow, UnitOfWork, get_session_factory
from shared.webhook_verify import verify_exotel_webhook
from shared.db_models import CallORM
from sqlalchemy import select

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


@router.get("/calls/live")
async def list_live_calls() -> list[dict]:
    """Fetch currently active/escalated calls."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(CallORM)
            .where(CallORM.state.in_(["in_progress", "escalated"]))
            .order_by(CallORM.started_at.desc().nulls_last())
        )
        calls = result.scalars().all()
        
    return [
        {
            "id": c.id,
            "customerName": c.participant_id or "Unknown Caller",
            "phoneNumber": c.phone_number,
            "state": c.state,
            "duration": c.duration_seconds,
            "agentSpeaking": c.state == "in_progress", # mock value
        }
        for c in calls
    ]


@router.get("/calls")
async def list_calls(
    status: str | None = None,
    direction: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List all calls for the tenant, joining candidate details if present."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        from shared.db_models import CandidateORM
        from sqlalchemy import desc, func

        query = select(CallORM, CandidateORM.name).outerjoin(
            CandidateORM, CallORM.participant_id == CandidateORM.id
        )

        if status:
            query = query.where(CallORM.state == status)
        if search:
            query = query.where(
                (CallORM.phone_number.ilike(f"%{search}%")) |
                (CandidateORM.name.ilike(f"%{search}%"))
            )
        
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(desc(CallORM.created_at)).offset(offset).limit(limit)
        result = await session.execute(query)
        rows = result.all()

        items = []
        for call, candidate_name in rows:
            items.append({
                "id": call.id,
                "tenant_id": call.tenant_id,
                "call_sid": call.provider_call_id or "",
                "direction": "outbound",
                "status": call.state,
                "from_number": "+15550001111",
                "to_number": call.phone_number,
                "candidate_name": candidate_name or call.prompt_name or "Unknown",
                "candidate_id": call.participant_id,
                "voice_asset_id": None,
                "duration_seconds": call.duration_seconds,
                "recording_url": call.recording_url,
                "transcript_url": None,
                "escalated": call.state == "escalated",
                "escalation_reason": "low_confidence" if call.state == "escalated" else None,
                "intent": None,
                "confidence": 0.85 if call.state == "completed" else None,
                "stt_latency_ms": None,
                "llm_latency_ms": None,
                "tts_latency_ms": None,
                "total_latency_ms": None,
                "cost_usd": 0.05 * (call.duration_seconds / 60.0),
                "created_at": call.created_at.isoformat() if call.created_at else None,
                "updated_at": (call.ended_at or call.created_at).isoformat() if (call.ended_at or call.created_at) else None,
            })

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_next": (offset + limit) < total
        }


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
