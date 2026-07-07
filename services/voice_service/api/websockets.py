"""
Voice Service WebSockets for Media Streaming.

Handles real-time audio streams (e.g., Twilio Media Streams or custom WebRTC).
"""
from __future__ import annotations

import asyncio
import json
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.voice_service.infrastructure.stream_manager import VoiceStreamManager

logger = structlog.get_logger("voice_service.websockets")

router = APIRouter(tags=["Voice Media"])

@router.websocket("/v1/voice/stream/{tenant_id}/{call_id}")
async def media_stream_endpoint(
    websocket: WebSocket,
    tenant_id: str,
    call_id: str,
    prompt_name: str = "general_hr_query_v1",
    prompt_version: str = "v1",
) -> None:
    """
    WebSocket endpoint for bidirectional audio streaming.
    
    Expects binary audio frames (or JSON wrapped base64 depending on provider).
    """
    await websocket.accept()
    logger.info("media_stream_connected", call_id=call_id, tenant_id=tenant_id)
    
    stream_manager = VoiceStreamManager(
        tenant_id=tenant_id,
        call_id=call_id,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
    )
    
    try:
        await stream_manager.initialize()
        
        while True:
            # Receive audio chunk from client/provider
            data = await websocket.receive_bytes()
            
            # Process through STT -> LLM -> TTS pipeline
            # Note: A production app would decouple receiving from processing
            # using asyncio Queues and tasks to allow full duplex interruption.
            response_audio = await stream_manager.process_audio_chunk(data)
            
            if response_audio:
                # Send generated audio back
                await websocket.send_bytes(response_audio)

    except WebSocketDisconnect:
        logger.info("media_stream_disconnected", call_id=call_id)
    except Exception as exc:
        logger.error("media_stream_error", call_id=call_id, error=str(exc))
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
