"""
Base CRM Adapter interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from shared.integration.base import BaseAdapter, IntegrationRequest


@dataclass
class CRMRequestData:
    """Standardized request format for CRM providers."""
    action: str  # e.g., "create_contact", "update_lead", "log_call"
    entity_type: str
    entity_id: str | None = None
    data: dict[str, Any] | None = None


@dataclass
class CRMResponseData:
    """Standardized response format for CRM providers."""
    success: bool
    entity_id: str | None
    provider_raw_response: dict[str, Any]


class BaseCRMAdapter(BaseAdapter[CRMResponseData]):
    """
    Abstract base for all CRM providers (HubSpot, Salesforce, Greenhouse).
    """

    @abc.abstractmethod
    async def sync(
        self,
        request: IntegrationRequest[CRMRequestData]
    ) -> CRMResponseData:
        """Execute a CRM synchronization action."""
        ...
