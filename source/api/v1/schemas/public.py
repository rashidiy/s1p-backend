"""
Public API schemas — API key management + public read-only endpoints
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


# ===== API Key Management Schemas =====

class ApiKeyCreateRequest(BaseModel):
    """Create API key request"""
    name: str = Field(..., min_length=1, max_length=255)


class ApiKeyCreateResponse(BaseModel):
    """Response when creating an API key — includes the full key (shown only once)"""
    id: UUID
    name: str
    key: str  # Full key, shown ONLY on creation
    key_prefix: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyResponse(BaseModel):
    """API key response (no full key)"""
    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyListResponse(BaseModel):
    """List of API keys"""
    items: List[ApiKeyResponse]
    total: int


# ===== Public API Paginated Response =====

class PublicPaginatedResponse(BaseModel):
    """Paginated response for public API (matches internal pattern)"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# ===== Public Entity Schemas (simplified, read-only) =====

class PublicContactResponse(BaseModel):
    """Contact in public API"""
    id: UUID
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    position: Optional[str] = None
    source: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicLeadResponse(BaseModel):
    """Lead in public API"""
    id: UUID
    title: str
    status: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    estimated_value: Optional[float] = None
    currency: Optional[str] = None
    contact_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    custom_fields: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicDealResponse(BaseModel):
    """Deal in public API"""
    id: UUID
    title: str
    stage: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    custom_fields: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicCallResponse(BaseModel):
    """Call event in public API"""
    id: int
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    direction: Optional[str] = None
    state: Optional[str] = None
    duration_sec: Optional[int] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
