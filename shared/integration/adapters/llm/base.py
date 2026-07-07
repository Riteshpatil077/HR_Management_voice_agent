"""
Base LLM Adapter interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from shared.integration.base import BaseAdapter, IntegrationRequest


@dataclass
class LLMMessage:
    """Standardized chat message."""
    role: str
    content: str


@dataclass
class LLMRequestData:
    """Standardized request format for all LLM providers."""
    messages: list[LLMMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 1024
    stop_sequences: list[str] = field(default_factory=list)


@dataclass
class LLMResponseData:
    """Standardized response format for all LLM providers."""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class BaseLLMAdapter(BaseAdapter[LLMResponseData]):
    """
    Abstract base for all LLM providers (OpenAI, Anthropic, Gemini).
    """

    @abc.abstractmethod
    async def chat(
        self,
        request: IntegrationRequest[LLMRequestData]
    ) -> LLMResponseData:
        """Execute a chat completion."""
        ...
