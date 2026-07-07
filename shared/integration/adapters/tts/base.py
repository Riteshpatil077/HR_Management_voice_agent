"""
Base Text-to-Speech (TTS) Adapter interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from shared.integration.base import BaseAdapter, IntegrationRequest


@dataclass
class TTSRequestData:
    """Standardized request format for TTS providers."""
    text: str
    voice_id: str
    language: str = "en"
    model: str = "eleven_multilingual_v2"
    optimize_streaming_latency: int = 2


@dataclass
class TTSResponseData:
    """Standardized response format for TTS providers."""
    audio_bytes: bytes
    content_type: str
    latency_ms: float


class BaseTTSAdapter(BaseAdapter[TTSResponseData]):
    """
    Abstract base for all TTS providers (ElevenLabs, Deepgram).
    """

    @abc.abstractmethod
    async def synthesize(
        self,
        request: IntegrationRequest[TTSRequestData]
    ) -> TTSResponseData:
        """Execute text synthesis into audio."""
        ...
