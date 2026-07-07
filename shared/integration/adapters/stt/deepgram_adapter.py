"""
Deepgram API Adapter for STT.
"""
from __future__ import annotations

import httpx
import structlog
from typing import Any

from shared.integration.adapters.stt.base import (
    BaseSTTAdapter,
    STTRequestData,
    STTResponseData,
)
from shared.integration.base import IntegrationRequest, ProviderHealth, ProviderStatus
from shared.settings import get_settings

logger = structlog.get_logger("integration.deepgram")
settings = get_settings()


class DeepgramAdapter(BaseSTTAdapter):
    """Adapter for Deepgram API."""
    
    provider_name = "deepgram"

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            base_url="https://api.deepgram.com/v1",
            headers={
                "Authorization": f"Token {settings.deepgram_api_key}",
            },
            timeout=60.0,
        )

    async def _call(self, request: IntegrationRequest[STTRequestData]) -> STTResponseData:
        """Raw API call to Deepgram."""
        params = {
            "model": request.payload.model,
            "language": request.payload.language,
            "smart_format": str(request.payload.smart_format).lower(),
            "punctuate": str(request.payload.punctuate).lower(),
        }

        if request.payload.audio_url:
            response = await self._client.post(
                "/listen",
                params=params,
                json={"url": request.payload.audio_url}
            )
        elif request.payload.audio_bytes:
            headers = {"Content-Type": "audio/wav"}
            response = await self._client.post(
                "/listen",
                params=params,
                headers=headers,
                content=request.payload.audio_bytes,
            )
        else:
            raise ValueError("Either audio_url or audio_bytes must be provided")

        response.raise_for_status()
        data = response.json()
        
        result = data["results"]["channels"][0]["alternatives"][0]
        metadata = data["metadata"]
        
        return STTResponseData(
            transcript=result["transcript"],
            confidence=result["confidence"],
            duration_seconds=metadata["duration"],
            words=result.get("words", []),
            language_detected=request.payload.language,
        )

    async def transcribe(self, request: IntegrationRequest[STTRequestData]) -> STTResponseData:
        """Public entry point for transcription."""
        response = await self.execute(request)
        return response.data

    async def health_check(self) -> ProviderHealth:
        """Check Deepgram API health."""
        try:
            response = await self._client.get("/projects")
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
        Calculate cost for Deepgram models.
        Nova-2 price: $0.0043 per minute.
        """
        if not isinstance(response_data, STTResponseData):
            return 0.0

        rate_per_min = 0.0043
        cost = (response_data.duration_seconds / 60.0) * rate_per_min
        return cost
