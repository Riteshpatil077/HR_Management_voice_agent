"""
Intelligent LLM Router.

Routes prompts to the optimal LLM provider based on cost, latency, 
and task complexity, falling back seamlessly if a provider fails.

Design Pattern: Strategy + Chain of Responsibility
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import Any

from shared.integration.factory import IntegrationFactory
from shared.integration.adapters.llm.base import LLMRequestData, LLMResponseData
from shared.integration.base import IntegrationRequest

logger = structlog.get_logger("llm_router")

@dataclass
class RoutePreference:
    """Preferences for LLM routing."""
    task_complexity: str = "medium"  # low, medium, high
    latency_sensitive: bool = True
    cost_sensitive: bool = True

class LLMRouter:
    """
    Dynamically routes LLM requests to the best available provider.
    """

    def __init__(self) -> None:
        pass

    def _select_provider(self, preference: RoutePreference) -> str:
        """
        Determine primary provider based on preference.
        """
        if preference.task_complexity == "high":
            # High reasoning tasks go to Claude 3.5 Sonnet (or GPT-4o)
            return "anthropic"
        elif preference.latency_sensitive and preference.cost_sensitive:
            # Low latency, low cost -> GPT-4o-mini / Haiku
            return "openai"
        return "openai"

    def _get_fallback_provider(self, primary: str) -> str:
        """Return the next best provider if primary fails."""
        fallbacks = {
            "openai": "anthropic",
            "anthropic": "openai",
        }
        return fallbacks.get(primary, "openai")

    async def chat(
        self,
        request_data: LLMRequestData,
        tenant_id: str,
        correlation_id: str,
        preference: RoutePreference | None = None
    ) -> LLMResponseData:
        """
        Execute chat request with automatic fallback.
        """
        pref = preference or RoutePreference()
        primary_provider = self._select_provider(pref)
        fallback_provider = self._get_fallback_provider(primary_provider)

        request = IntegrationRequest(
            provider=primary_provider,
            operation="chat_completion",
            payload=request_data,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
        )

        try:
            adapter = IntegrationFactory.get_llm_adapter(tenant_id, primary_provider)
            return await adapter.chat(request)
        except Exception as exc:
            logger.warning(
                "primary_llm_failed",
                primary=primary_provider,
                fallback=fallback_provider,
                error=str(exc),
                correlation_id=correlation_id,
            )
            # Try fallback
            fallback_request = IntegrationRequest(
                provider=fallback_provider,
                operation="chat_completion",
                payload=request_data,
                tenant_id=tenant_id,
                correlation_id=correlation_id,
            )
            fallback_adapter = IntegrationFactory.get_llm_adapter(tenant_id, fallback_provider)
            return await fallback_adapter.chat(fallback_request)

_router = LLMRouter()

def get_llm_router() -> LLMRouter:
    return _router
