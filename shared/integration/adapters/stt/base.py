"""
Base Speech-to-Text (STT) Adapter interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from shared.integration.base import BaseAdapter, IntegrationRequest


@dataclass
class STTRequestData:
    """Standardized request format for STT providers."""
    audio_url: str | None = None
    audio_bytes: bytes | None = None
    language: str = "hi"
    model: str = "nova-2"
    smart_format: bool = True
    punctuate: bool = True


@dataclass
class STTResponseData:
    """Standardized response format for STT providers."""
    transcript: str
    confidence: float
    duration_seconds: float
    words: list[dict[str, Any]]
    language_detected: str


class BaseSTTAdapter(BaseAdapter[STTResponseData]):
    """
    Abstract base for all STT providers (Deepgram, AssemblyAI).
    """

    @abc.abstractmethod
    async def transcribe(
        self,
        request: IntegrationRequest[STTRequestData]
    ) -> STTResponseData:
        """Execute audio transcription."""
        ...
