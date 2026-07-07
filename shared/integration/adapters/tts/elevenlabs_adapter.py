"""
ElevenLabs API Adapter for TTS.
"""
from __future__ import annotations

import time
import httpx
import structlog
from typing import Any

from shared.integration.adapters.tts.base import (
    BaseTTSAdapter,
    TTSRequestData,
    TTSResponseData,
)
from shared.integration.base import IntegrationRequest, ProviderHealth, ProviderStatus
from shared.settings import get_settings

logger = structlog.get_logger("integration.elevenlabs")
settings = get_settings()


class ElevenLabsAdapter(BaseTTSAdapter):
    """Adapter for ElevenLabs API."""
    
    provider_name = "elevenlabs"

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            base_url="https://api.elevenlabs.io/v1",
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def _call(self, request: IntegrationRequest[TTSRequestData]) -> TTSResponseData:
        """Raw API call to ElevenLabs."""
        start = time.perf_counter()
        
        payload = {
            "text": request.payload.text,
            "model_id": request.payload.model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            }
        }
        
        params = {}
        if request.payload.optimize_streaming_latency > 0:
            params["optimize_streaming_latency"] = request.payload.optimize_streaming_latency

        voice_id = request.payload.voice_id
        response = await self._client.post(
            f"/text-to-speech/{voice_id}",
            json=payload,
            params=params,
        )
        response.raise_for_status()
        
        latency = (time.perf_counter() - start) * 1000
        
        return TTSResponseData(
            audio_bytes=response.content,
            content_type=response.headers.get("Content-Type", "audio/mpeg"),
            latency_ms=latency,
        )

    async def synthesize(self, request: IntegrationRequest[TTSRequestData]) -> TTSResponseData:
        """Public entry point for text synthesis."""
        response = await self.execute(request)
        return response.data

    async def health_check(self) -> ProviderHealth:
        """Check ElevenLabs API health."""
        try:
            # simple voices fetch for healthcheck
            response = await self._client.get("/voices")
            response.raise_for_status()
            return ProviderHealth(
                provider=self.provider_name,
                status=ProviderStatus.HEALTHY,
                latency_ms=response.elapsed.total_seconds() * 1000,
                error_rate=0.0,
            )
        except Exception:
            return ProviderHealth(
                provider=self.provider_name,
                status=ProviderStatus.UNHEALTHY,
                latency_ms=0,
                error_rate=1.0,
            )

    def calculate_cost(self, response_data: Any) -> float:
        """
        Calculate cost for ElevenLabs models.
        Price is ~$0.18 per 1000 characters (Creator plan).
        Since we only have audio output, we can estimate based on audio length
        or if we had the input text, we could measure it.
        For simplicity, assume a flat rate per request or fetch from response headers if available.
        """
        # Actually Elevenlabs returns 'character-count' header sometimes, but we don't extract it.
        # Fallback to a rough estimate: 1 second of audio ~ 15 chars.
        return 0.005  # fixed estimate for now
