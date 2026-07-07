"""
OpenAI API Adapter.
"""
from __future__ import annotations

import httpx
import structlog
from typing import Any

from shared.integration.adapters.llm.base import (
    BaseLLMAdapter,
    LLMRequestData,
    LLMResponseData,
)
from shared.integration.base import IntegrationRequest, ProviderHealth, ProviderStatus
from shared.settings import get_settings

logger = structlog.get_logger("integration.openai")
settings = get_settings()


class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for OpenAI API."""
    
    provider_name = "openai"

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=30.0,
        )

    async def _call(self, request: IntegrationRequest[LLMRequestData]) -> LLMResponseData:
        """Raw API call to OpenAI."""
        payload = {
            "model": request.payload.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.payload.messages],
            "temperature": request.payload.temperature,
            "max_tokens": request.payload.max_tokens,
        }

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        return LLMResponseData(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            input_tokens=data["usage"]["prompt_tokens"],
            output_tokens=data["usage"]["completion_tokens"],
            finish_reason=data["choices"][0]["finish_reason"],
        )

    async def chat(self, request: IntegrationRequest[LLMRequestData]) -> LLMResponseData:
        """Public entry point for chat completion."""
        response = await self.execute(request)
        return response.data

    async def health_check(self) -> ProviderHealth:
        """Check OpenAI API health."""
        try:
            response = await self._client.get("/models")
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
        Calculate cost for OpenAI models.
        Prices per 1M tokens (as of late 2024 approximation).
        """
        if not isinstance(response_data, LLMResponseData):
            return 0.0

        rates = {
            "gpt-4o": {"in": 5.0, "out": 15.0},
            "gpt-4o-mini": {"in": 0.15, "out": 0.60},
        }

        model = response_data.model
        # Use gpt-4o rates as fallback if model string contains a date suffix
        rate = rates.get(model)
        if not rate:
            for key, val in rates.items():
                if key in model:
                    rate = val
                    break
            else:
                rate = {"in": 0.0, "out": 0.0}

        cost = (response_data.input_tokens / 1_000_000 * rate["in"]) + \
               (response_data.output_tokens / 1_000_000 * rate["out"])
        return cost
