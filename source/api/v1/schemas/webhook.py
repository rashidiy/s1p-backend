"""
Outbound webhook schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

VALID_EVENTS = [
    "call.completed",
    "call.missed",
    "lead.created",
    "deal.stage_changed",
    "contact.created",
]


class WebhookEndpointCreate(BaseModel):
    url: str = Field(..., max_length=2048)
    events: List[str] = Field(..., min_length=1)
    secret: str = Field(..., min_length=16, max_length=255)

    def model_post_init(self, __context):
        invalid = [e for e in self.events if e not in VALID_EVENTS]
        if invalid:
            raise ValueError(f"Invalid events: {invalid}. Valid: {VALID_EVENTS}")


class WebhookEndpointUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=2048)
    events: Optional[List[str]] = None
    secret: Optional[str] = Field(None, min_length=16, max_length=255)
    is_active: Optional[bool] = None

    def model_post_init(self, __context):
        if self.events is not None:
            invalid = [e for e in self.events if e not in VALID_EVENTS]
            if invalid:
                raise ValueError(f"Invalid events: {invalid}. Valid: {VALID_EVENTS}")


class WebhookEndpointResponse(BaseModel):
    id: UUID
    company_id: UUID
    url: str
    events: List[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WebhookDeliveryResponse(BaseModel):
    id: UUID
    endpoint_id: UUID
    event_type: str
    payload: dict
    status: str
    attempts: int
    last_attempt_at: Optional[datetime]
    response_code: Optional[int]
    response_body: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
