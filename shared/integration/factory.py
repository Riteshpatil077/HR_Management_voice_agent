"""
Integration Factory.

Provides a unified factory to get the correct adapter for a given tenant.
Supports tenant-specific provider overrides.
"""
from __future__ import annotations

from shared.integration.adapters.llm.base import BaseLLMAdapter
from shared.integration.adapters.llm.openai_adapter import OpenAIAdapter
from shared.integration.adapters.llm.anthropic_adapter import AnthropicAdapter
from shared.integration.adapters.stt.base import BaseSTTAdapter
from shared.integration.adapters.stt.deepgram_adapter import DeepgramAdapter
from shared.integration.adapters.telephony.base import BaseTelephonyAdapter
from shared.integration.adapters.telephony.exotel_adapter import ExotelAdapter
from shared.settings import get_settings

settings = get_settings()

_llm_adapters = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
}

_stt_adapters = {
    "deepgram": DeepgramAdapter(),
}

_telephony_adapters = {
    "exotel": ExotelAdapter(),
}

class IntegrationFactory:
    """
    Factory to retrieve integration adapters.
    
    Future: Could check tenant-specific configurations (e.g., in PostgreSQL or Vault)
    to return a provider specific to a tenant.
    """

    @staticmethod
    def get_llm_adapter(tenant_id: str, preferred_provider: str = "openai") -> BaseLLMAdapter:
        """Get LLM adapter for a tenant."""
        # Here we could check if tenant_id has a specific provider configured.
        # Defaulting to preferred_provider for now.
        adapter = _llm_adapters.get(preferred_provider)
        if not adapter:
            raise ValueError(f"Unsupported LLM provider: {preferred_provider}")
        return adapter

    @staticmethod
    def get_stt_adapter(tenant_id: str, preferred_provider: str = "deepgram") -> BaseSTTAdapter:
        """Get STT adapter for a tenant."""
        adapter = _stt_adapters.get(preferred_provider)
        if not adapter:
            raise ValueError(f"Unsupported STT provider: {preferred_provider}")
        return adapter

    @staticmethod
    def get_telephony_adapter(tenant_id: str, preferred_provider: str = "exotel") -> BaseTelephonyAdapter:
        """Get Telephony adapter for a tenant."""
        adapter = _telephony_adapters.get(preferred_provider)
        if not adapter:
            raise ValueError(f"Unsupported Telephony provider: {preferred_provider}")
        return adapter
