"""
Call/Telephony schemas
"""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, computed_field
from api.v1.schemas.common.base import BaseSchema, TimestampMixin
from db.models.enums import CallStatusEnum, CallDirectionEnum, ProviderEnum, CallOutcomeEnum


class CallRequest(BaseModel):
    """Request to call from external number to external number"""
    phone_1: str = Field(..., description="First phone number (caller)")
    phone_2: str = Field(..., description="Second phone number (receiver)")
    operator_id: Optional[str] = Field(None, description="Operator identifier: UUID, phone, email, or SIP number")
    order_id: Optional[str] = Field(None, description="External order/ticket ID")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallNumberRequest(BaseModel):
    """Request to call from internal SIP extension to external phone"""
    phone: str = Field(..., description="External phone number to call")
    operator_id: str = Field(..., description="Operator identifier: UUID, phone, email, or SIP number")
    reverse: bool = Field(False, description="Call order: False = internal first, True = external first")
    antiaon: bool = Field(False, description="Hide caller ID")
    order_id: Optional[str] = Field(None, description="External order/ticket ID")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallTreeRequest(BaseModel):
    """Request to call external number through a call tree/scheme"""
    phone: str = Field(..., description="External phone number to call")
    operator_id: str = Field(..., description="Operator identifier: UUID, phone, email, or SIP number")
    tree: str = Field(..., description="Call tree/scheme identifier (e.g., '000-913898')")
    reverse: bool = Field(False, description="Call order: False = external first, True = tree first")
    call_attempt_time: int = Field(30, ge=30, description="Attempt duration in seconds (min 30)")
    order_id: Optional[str] = Field(None, description="External order/ticket ID")
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class CallResponse(BaseModel):
    """Response from call initiation"""
    success: bool
    call_id: Optional[int] = Field(None, description="Company-scoped call number")
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


class CallEventResponse(BaseSchema, TimestampMixin):
    """Call event response"""
    id: int
    company_id: UUID
    provider_type: ProviderEnum
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    operator_id: Optional[UUID] = None
    direction: Optional[CallDirectionEnum] = None
    state: Optional[CallStatusEnum] = None
    attempts: int
    waiting_sec: Optional[int] = None
    billing_sec: Optional[int] = None
    call_start_timestamp: Optional[int] = None
    call_end_timestamp: Optional[int] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    outcome: Optional[CallOutcomeEnum] = None
    disposition_notes: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    record_url: Optional[str] = Field(None, exclude=True)

    @computed_field
    @property
    def has_recording(self) -> bool:
        return self.record_url is not None


__all__ = [
    "CallRequest",
    "CallNumberRequest",
    "CallTreeRequest",
    "CallResponse",
    "CallEventCreate",
    "CallEventResponse",
]
