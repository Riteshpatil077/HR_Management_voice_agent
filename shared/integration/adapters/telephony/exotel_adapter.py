"""
Exotel API Adapter for Telephony.
"""
from __future__ import annotations

import httpx
import structlog
from typing import Any

from shared.integration.adapters.telephony.base import (
    BaseTelephonyAdapter,
    TelephonyRequestData,
    TelephonyResponseData,
)
from shared.integration.base import IntegrationRequest, ProviderHealth, ProviderStatus
from shared.settings import get_settings

logger = structlog.get_logger("integration.exotel")
settings = get_settings()


class ExotelAdapter(BaseTelephonyAdapter):
    """Adapter for Exotel API."""
    
    provider_name = "exotel"

    def __init__(self) -> None:
        super().__init__()
        self._sid = settings.exotel_account_sid
        self._token = settings.exotel_api_token
        self._subdomain = settings.exotel_subdomain
        
        base_url = f"https://{self._sid}:{self._token}@{self._subdomain}/v1/Accounts/{self._sid}"
        
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30.0,
        )

    async def _call(self, request: IntegrationRequest[TelephonyRequestData]) -> TelephonyResponseData:
        """Raw API call to Exotel."""
        data = {
            "From": request.payload.from_number,
            "To": request.payload.to_number,
            "Url": request.payload.callback_url,
        }
        
        if request.payload.custom_field:
            data["CustomField"] = request.payload.custom_field
            
        if request.payload.time_limit_seconds:
            data["TimeLimit"] = str(request.payload.time_limit_seconds)

        response = await self._client.post("/Calls/connect.json", data=data)
        response.raise_for_status()
        
        json_data = response.json()
        call_sid = json_data["Call"]["Sid"]
        status = json_data["Call"]["Status"]
        
        return TelephonyResponseData(
            call_id=call_sid,
            status=status,
            provider_raw_response=json_data,
        )

    async def initiate_call(self, request: IntegrationRequest[TelephonyRequestData]) -> TelephonyResponseData:
        """Public entry point for initiating a call."""
        response = await self.execute(request)
        return response.data

    async def health_check(self) -> ProviderHealth:
        """Check Exotel API health."""
        try:
            # A simple GET request to check account details
            response = await self._client.get("/")
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
        Calculate cost for Exotel.
        Normally, actual cost is derived from the webhook after call completion,
        so initiation cost is 0.0 unless there is a flat connection fee.
        """
        return 0.0
