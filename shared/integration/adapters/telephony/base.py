"""
Base Telephony Adapter interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from shared.integration.base import BaseAdapter, IntegrationRequest


@dataclass
class TelephonyRequestData:
    """Standardized request format for telephony providers."""
    to_number: str
    from_number: str
    callback_url: str
    custom_field: str | None = None
    time_limit_seconds: int | None = None


@dataclass
class TelephonyResponseData:
    """Standardized response format for telephony providers."""
    call_id: str
    status: str
    provider_raw_response: dict[str, Any]


class BaseTelephonyAdapter(BaseAdapter[TelephonyResponseData]):
    """
    Abstract base for all telephony providers (Exotel, Twilio).
    """

    @abc.abstractmethod
    async def initiate_call(
        self,
        request: IntegrationRequest[TelephonyRequestData]
    ) -> TelephonyResponseData:
        """Initiate an outbound call."""
        ...
