"""
Base abstract class for telephony providers
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class CallRequest(BaseModel):
    """Call initiation request"""
    phone_1: str = Field(..., description="First phone number (caller or external)")
    phone_2: str = Field(..., description="Second phone number (receiver or internal)")
    operator_id: Optional[str] = Field(None, description="Operator/user ID")
    order_id: Optional[str] = Field(None, description="External order/ticket ID")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallResponse(BaseModel):
    """Call initiation response"""
    success: bool
    call_id: str = Field(..., description="Provider's call ID")
    message: Optional[str] = None
    error: Optional[str] = None


class CallStatus(BaseModel):
    """Call status information"""
    provider_call_id: str
    state: Optional[str] = None
    waiting_sec: Optional[int] = None
    billing_sec: Optional[int] = None
    record_url: Optional[str] = None
    call_start: Optional[datetime] = None
    call_end: Optional[datetime] = None
    disposition: Optional[str] = None


class CallHistoryRequest(BaseModel):
    """Request for call history"""
    time_from: Optional[datetime] = None
    time_to: Optional[datetime] = None
    operator_id: Optional[str] = None
    order_id: Optional[str] = None
    limit: Optional[int] = 100
    offset: Optional[int] = 0


class TelephonyProvider(ABC):
    """
    Abstract base class for telephony providers

    All telephony providers (Sipuni, Binotel, etc.) must implement this interface.
    This ensures a consistent API across different providers.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with company-specific configuration

        Args:
            config: Provider configuration from companies.provider_config
                    Structure varies by provider
        """
        self.config = config

    @abstractmethod
    async def make_call(self, request: CallRequest) -> CallResponse:
        """
        Initiate a call

        Args:
            request: Call request parameters

        Returns:
            CallResponse with success status and call_id

        Raises:
            ProviderException: If API call fails
        """
        pass

    @abstractmethod
    async def get_call_status(self, call_id: str) -> Optional[CallStatus]:
        """
        Get call status by provider_call_id

        Args:
            call_id: Provider's call identifier

        Returns:
            CallStatus object or None if not found
        """
        pass

    @abstractmethod
    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """
        Get call recording URL

        Args:
            call_id: Provider's call identifier

        Returns:
            Recording URL or None if not available
        """
        pass

    @abstractmethod
    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process incoming webhook from provider

        Args:
            payload: Webhook payload (POST data or JSON)
            headers: HTTP headers

        Returns:
            Normalized call event data or None if not a valid webhook
            Format:
            {
                "provider_call_id": str,
                "phone_1": str,
                "phone_2": str,
                "state": str,
                "billing_sec": int,
                "waiting_sec": int,
                "record_url": str,
                "call_start_timestamp": int,
                "call_end_timestamp": int,
                "direction": str,
                ...
            }
        """
        pass

    @abstractmethod
    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate webhook authentication

        Args:
            payload: Webhook payload
            headers: HTTP headers

        Returns:
            True if webhook is authentic
        """
        pass

    async def get_call_history(
        self,
        request: CallHistoryRequest
    ) -> List[Dict[str, Any]]:
        """
        Get call history (optional, not all providers support this)

        Args:
            request: Call history filter parameters

        Returns:
            List of call records
        """
        return []


class ProviderException(Exception):
    """Exception raised by telephony providers"""

    def __init__(self, message: str, provider: str, details: Optional[Dict] = None):
        self.message = message
        self.provider = provider
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        return f"[{self.provider}] {self.message}"
