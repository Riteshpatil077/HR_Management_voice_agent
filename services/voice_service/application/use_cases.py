"""
Application Use Cases for Voice Service.

Orchestrates domain logic and infrastructure.
"""
from __future__ import annotations

import structlog

from services.voice_service.domain.models import Call, CallContext, CallParticipant, CallState
from services.voice_service.infrastructure.repositories import CallRepository
from shared.domain_events import CallCompleted, CallFailed, CallInitiated, get_event_bus
from shared.integration.adapters.telephony.base import TelephonyRequestData
from shared.integration.factory import IntegrationFactory
from shared.integration.base import IntegrationRequest
from shared.unit_of_work import UnitOfWork

logger = structlog.get_logger("voice_service.use_cases")

class InitiateCallUseCase:
    """Use case to initiate an outbound voice call."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        tenant_id: str,
        phone_number: str,
        participant_role: str,
        prompt_name: str,
        prompt_version: str,
        variables: dict[str, str],
        participant_id: str | None = None,
    ) -> str:
        """
        Initiate a call and return the internal Call ID.
        """
        participant = CallParticipant(
            phone_number=phone_number,
            role=participant_role,
            id=participant_id,
        )
        context = CallContext(
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            variables=variables,
        )
        call = Call(tenant_id=tenant_id, participant=participant, context=context)

        # Use Telephony Adapter to make the actual call
        telephony = IntegrationFactory.get_telephony_adapter(tenant_id)
        
        # Hardcoding the from_number and callback URL for this demo.
        # In a real app, these would come from tenant settings.
        req_data = TelephonyRequestData(
            to_number=phone_number,
            from_number="+1234567890", # Replace with tenant's number
            callback_url=f"https://api.yourdomain.com/v1/voice/webhooks/exotel/{tenant_id}",
            custom_field=call.id,
        )
        
        try:
            req = IntegrationRequest(
                provider=telephony.provider_name,
                operation="initiate_call",
                payload=req_data,
                tenant_id=tenant_id,
                correlation_id=call.id,
            )
            resp = await telephony.initiate_call(req)
            call.mark_ringing(resp.call_id)
            
            async with self.uow as uow:
                repo = CallRepository(uow.session)
                repo.add(call)
                
                # Emit Domain Event
                uow.collect_event(
                    CallInitiated(
                        call_id=call.id,
                        candidate_phone=phone_number,
                        tenant_id=tenant_id,
                        correlation_id=call.id
                    )
                )
                await uow.commit()
                
            return call.id

        except Exception as exc:
            logger.error("call_initiation_failed", call_id=call.id, error=str(exc))
            call.mark_failed(str(exc))
            async with self.uow as uow:
                repo = CallRepository(uow.session)
                repo.add(call)
                uow.collect_event(
                    CallFailed(
                        call_id=call.id,
                        reason=str(exc),
                        tenant_id=tenant_id,
                        correlation_id=call.id
                    )
                )
                await uow.commit()
            raise
