"""
Versioned Prompt Registry.

Loads and caches LLM prompts. Prompts can be loaded from files
or database. Allows hot-reloading without service restart.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from shared.cache import CacheClient
from shared.settings import get_settings

logger = structlog.get_logger("prompt_registry")
settings = get_settings()

_PROMPTS: dict[str, str] = {
    # Default fallback prompts if DB/S3 fails
    "general_hr_query_v1": "You are an HR assistant. Answer the user's question concisely.",
    "interview_confirmation_v1": "You are calling to confirm an interview with a candidate.",
    "document_reminder_v1": "You are calling to remind the employee to submit their onboarding documents.",
    "intent_router_v1": "Determine the user's intent from their utterance. Return JSON.",
}


class PromptRegistry:
    """
    Registry for LLM prompts.

    In production, this could fetch from a database or S3 and cache the result,
    allowing prompts to be updated by ops without deploying new code.
    """
    def __init__(self) -> None:
        self._cache = CacheClient("prompts", "system")
        self._lock = asyncio.Lock()

    async def get_prompt(self, prompt_name: str, version: str = "v1") -> str:
        """
        Get a prompt template by name and version.
        """
        key = f"{prompt_name}_{version}"
        
        # 1. Try local memory cache (simulated by the static dict for now)
        if key in _PROMPTS:
            return _PROMPTS[key]

        # 2. Try Redis cache
        cached = await self._cache.get(key)
        if cached:
            return str(cached)

        # 3. Fallback to hardcoded defaults or raise
        logger.error("prompt_not_found", prompt_name=prompt_name, version=version)
        raise ValueError(f"Prompt {key} not found in registry")

    async def update_prompt(self, prompt_name: str, version: str, content: str) -> None:
        """
        Update a prompt in the registry.
        """
        key = f"{prompt_name}_{version}"
        async with self._lock:
            _PROMPTS[key] = content
            await self._cache.set(key, content, ttl=86400)
            logger.info("prompt_updated", prompt_name=prompt_name, version=version)


_registry = PromptRegistry()


def get_prompt_registry() -> PromptRegistry:
    return _registry
