"""
Anthropic API Adapter.
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

logger = structlog.get_logger("integration.anthropic")
settings = get_settings()


class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for Anthropic API."""
    
    provider_name = "anthropic"

    def __init__(self) -> None:
        super().__init__()
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            timeout=30.0,
        )

    async def _call(self, request: IntegrationRequest[LLMRequestData]) -> LLMResponseData:
        """Raw API call to Anthropic."""
        # Convert standard LLMRequestData messages to Anthropic's format
        system_prompt = ""
        anthropic_messages = []
        for m in request.payload.messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                anthropic_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": request.payload.model,
            "messages": anthropic_messages,
            "max_tokens": request.payload.max_tokens,
            "temperature": request.payload.temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = await self._client.post("/messages", json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        return LLMResponseData(
            content=data["content"][0]["text"],
            model=data["model"],
            input_tokens=data["usage"]["input_tokens"],
            output_tokens=data["usage"]["output_tokens"],
            finish_reason=data["stop_reason"],
        )

    async def chat(self, request: IntegrationRequest[LLMRequestData]) -> LLMResponseData:
        """Public entry point for chat completion."""
        response = await self.execute(request)
        return response.data

    async def health_check(self) -> ProviderHealth:
        """Check Anthropic API health."""
        # Anthropic doesn't have a standard health endpoint, using a minimal call
        # or checking network connectivity. We'll simulate a fast failing call or just return Healthy.
        try:
            response = await self._client.get("/")
            # The root endpoint usually returns a 404 or a JSON error, but responds quickly.
            # If we get a response (even 4xx), the service is reachable.
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
        Calculate cost for Anthropic models.
        Prices per 1M tokens.
        """
        if not isinstance(response_data, LLMResponseData):
            return 0.0

        rates = {
            "claude-3-5-sonnet-20240620": {"in": 3.0, "out": 15.0},
            "claude-3-haiku-20240307": {"in": 0.25, "out": 1.25},
        }

        model = response_data.model
        rate = rates.get(model, {"in": 3.0, "out": 15.0})  # Fallback to Sonnet pricing

        cost = (response_data.input_tokens / 1_000_000 * rate["in"]) + \
               (response_data.output_tokens / 1_000_000 * rate["out"])
        return cost
