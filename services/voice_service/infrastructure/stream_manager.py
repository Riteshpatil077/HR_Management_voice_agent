"""
Voice Stream Manager.

Orchestrates real-time audio streams between the telephony provider,
STT provider, LLM, and TTS provider.
"""
from __future__ import annotations

import asyncio
import structlog
from typing import AsyncGenerator

from shared.integration.factory import IntegrationFactory
from shared.integration.base import IntegrationRequest
from shared.integration.adapters.stt.base import STTRequestData
from shared.integration.adapters.tts.base import TTSRequestData
from shared.integration.adapters.llm.base import LLMRequestData, LLMMessage
from shared.llm_router import get_llm_router
from shared.prompt_registry import get_prompt_registry
from shared.guardrails import get_guardrail_pipeline

logger = structlog.get_logger("voice_service.stream")

class VoiceStreamManager:
    """
    Manages the full duplex audio stream for a voice call.
    Receives audio chunks, runs STT, generates LLM response, runs TTS,
    and returns audio chunks back to the telephony provider.
    """

    def __init__(self, tenant_id: str, call_id: str, prompt_name: str, prompt_version: str):
        self.tenant_id = tenant_id
        self.call_id = call_id
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        
        self.stt = IntegrationFactory.get_stt_adapter(tenant_id)
        self.tts = IntegrationFactory.get_tts_adapter(tenant_id)
        self.llm = get_llm_router()
        self.registry = get_prompt_registry()
        self.guardrails = get_guardrail_pipeline()
        
        self.chat_history: list[LLMMessage] = []

    async def initialize(self) -> None:
        """Load initial prompt and context."""
        system_prompt = await self.registry.get_prompt(self.prompt_name, self.prompt_version)
        self.chat_history.append(LLMMessage(role="system", content=system_prompt))
        
        # Initial greeting from agent
        # We could generate this dynamically or use a pre-defined string
        # For simplicity in this skeleton, we'll wait for the user to speak.

    async def process_audio_chunk(self, audio_bytes: bytes) -> bytes | None:
        """
        Process incoming audio bytes.
        
        Note: In a real streaming implementation, this would buffer audio,
        use a streaming STT connection (WebSockets), and stream TTS back.
        For this simplified architectural example, we simulate a turn-based interaction.
        """
        try:
            # 1. STT
            stt_req = IntegrationRequest(
                provider=self.stt.provider_name,
                operation="transcribe",
                payload=STTRequestData(audio_bytes=audio_bytes),
                tenant_id=self.tenant_id,
                correlation_id=self.call_id,
            )
            stt_resp = await self.stt.transcribe(stt_req)
            user_text = stt_resp.transcript
            
            if not user_text.strip():
                return None
                
            self.chat_history.append(LLMMessage(role="user", content=user_text))
            
            # 2. LLM Generation
            llm_req_data = LLMRequestData(
                messages=self.chat_history,
                model="gpt-4o-mini", # The router will override this based on preference anyway
                max_tokens=150,
            )
            llm_resp = await self.llm.chat(
                request_data=llm_req_data,
                tenant_id=self.tenant_id,
                correlation_id=self.call_id
            )
            agent_text = llm_resp.content
            
            # 3. Guardrails
            guard_result = await self.guardrails.run(
                response=agent_text,
                tenant_id=self.tenant_id,
            )
            safe_text = guard_result.sanitized
            self.chat_history.append(LLMMessage(role="assistant", content=safe_text))
            
            # 4. TTS
            tts_req = IntegrationRequest(
                provider=self.tts.provider_name,
                operation="synthesize",
                payload=TTSRequestData(
                    text=safe_text,
                    voice_id="default",
                ),
                tenant_id=self.tenant_id,
                correlation_id=self.call_id,
            )
            tts_resp = await self.tts.synthesize(tts_req)
            
            return tts_resp.audio_bytes

        except Exception as exc:
            logger.error("stream_processing_error", call_id=self.call_id, error=str(exc))
            # Fallback audio or silence could be returned here
            return None
