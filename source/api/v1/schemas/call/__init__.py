"""
Call/Telephony schemas
"""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from api.v1.schemas.common.base import BaseSchema, TimestampMixin, UUIDMixin
from db.models.enums import CallStatusEnum, CallDirectionEnum, ProviderEnum


class CallRequest(BaseModel):
    """Request to initiate a call"""
    phone_1: str = Field(..., description="First phone number (caller or external)")
    phone_2: str = Field(..., description="Second phone number (receiver or internal)")
    operator_id: Optional[UUID] = Field(None, description="Operator/user ID")
    order_id: Optional[str] = Field(None, description="External order/ticket ID")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallResponse(BaseModel):
    """Response from call initiation"""
    success: bool
    call_id: str = Field(..., description="Provider's call ID")
    message: Optional[str] = None
    error: Optional[str] = None


class CallEventCreate(BaseModel):
    """Create call event"""
    provider_call_id: str
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    operator_id: Optional[UUID] = None
    direction: Optional[CallDirectionEnum] = None
    state: Optional[CallStatusEnum] = None
    attempts: int = 1
    waiting_sec: Optional[int] = None
    billing_sec: Optional[int] = None
    record_url: Optional[str] = None
    call_start_timestamp: Optional[int] = None
    call_end_timestamp: Optional[int] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallEventResponse(BaseSchema, UUIDMixin, TimestampMixin):
    """Call event response"""
    company_id: UUID
    provider_type: ProviderEnum
    provider_call_id: str
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    operator_id: Optional[UUID] = None
    direction: Optional[CallDirectionEnum] = None
    state: Optional[CallStatusEnum] = None
    attempts: int
    waiting_sec: Optional[int] = None
    billing_sec: Optional[int] = None
    record_url: Optional[str] = None
    call_start_timestamp: Optional[int] = None
    call_end_timestamp: Optional[int] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None


class CallRecordingURL(BaseModel):
    """Call recording URL response"""
    url: str
    expires_in: int


__all__ = [
    "CallRequest",
    "CallResponse",
    "CallEventCreate",
    "CallEventResponse",
    "CallRecordingURL",
]
