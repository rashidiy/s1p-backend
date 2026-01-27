"""
CRM schemas for Contacts, Leads, Deals, Tasks, Notes
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date
from pydantic import BaseModel, EmailStr, Field


# ===== Contact Schemas =====

class ContactBase(BaseModel):
    """Base contact schema"""
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = Field(None, max_length=100)
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ContactCreateRequest(ContactBase):
    """Create contact request"""
    tags: Optional[List[str]] = Field(default_factory=list)


class ContactUpdateRequest(BaseModel):
    """Update contact request"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = Field(None, max_length=100)
    custom_fields: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class ContactResponse(ContactBase):
    """Contact response"""
    id: UUID
    company_id: UUID
    created_by: Optional[UUID]
    assigned_to: Optional[UUID] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    # Related counts
    total_leads: int = 0
    total_deals: int = 0
    total_calls: int = 0

    class Config:
        from_attributes = True


# ===== Lead Schemas =====

class LeadBase(BaseModel):
    """Base lead schema"""
    title: str = Field(..., min_length=1, max_length=255)
    contact_id: Optional[UUID] = None
    source: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    estimated_value: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field("USD", max_length=10)
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)


class LeadCreateRequest(LeadBase):
    """Create lead request"""
    assigned_to: Optional[UUID] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class LeadUpdateRequest(BaseModel):
    """Update lead request"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    source: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    estimated_value: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    custom_fields: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class LeadResponse(LeadBase):
    """Lead response"""
    id: UUID
    company_id: UUID
    status: Optional[str] = None
    pipeline_stage: Optional[str] = None
    assigned_to: Optional[UUID] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    # Related info
    contact_name: Optional[str] = None
    assigned_to_name: Optional[str] = None

    class Config:
        from_attributes = True


# ===== Deal Schemas =====

class DealBase(BaseModel):
    """Base deal schema"""
    title: str = Field(..., min_length=1, max_length=255)
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    amount: float = Field(..., ge=0)
    currency: Optional[str] = Field("USD", max_length=10)
    probability: Optional[int] = Field(0, ge=0, le=100)
    expected_close_date: Optional[date] = None
    description: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DealCreateRequest(DealBase):
    """Create deal request"""
    assigned_to: Optional[UUID] = None
    tags: Optional[List[str]] = Field(default_factory=list)


class DealUpdateRequest(BaseModel):
    """Update deal request"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    assigned_to: Optional[UUID] = None
    amount: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=10)
    probability: Optional[int] = Field(None, ge=0, le=100)
    expected_close_date: Optional[date] = None
    description: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class DealResponse(DealBase):
    """Deal response"""
    id: UUID
    company_id: UUID
    stage: Optional[str] = None
    assigned_to: Optional[UUID] = None
    tags: Optional[List[str]] = None
    closed_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    # Related info
    contact_name: Optional[str] = None
    assigned_to_name: Optional[str] = None
    weighted_value: float = 0.0  # amount * probability / 100

    class Config:
        from_attributes = True


# ===== Task Schemas =====

class TaskBase(BaseModel):
    """Base task schema"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: Optional[datetime] = None

    # Link to entities (polymorphic)
    entity_type: Optional[str] = Field(None, max_length=50)  # 'lead', 'contact', 'deal'
    entity_id: Optional[UUID] = None


class TaskCreateRequest(TaskBase):
    """Create task request"""
    assigned_to: Optional[UUID] = None


class TaskUpdateRequest(BaseModel):
    """Update task request"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    assigned_to: Optional[UUID] = None
    entity_type: Optional[str] = Field(None, max_length=50)
    entity_id: Optional[UUID] = None


class TaskResponse(TaskBase):
    """Task response"""
    id: UUID
    company_id: UUID
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[UUID] = None
    created_by: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Related info
    assigned_to_name: Optional[str] = None

    class Config:
        from_attributes = True


# ===== Note Schemas =====

class NoteBase(BaseModel):
    """Base note schema"""
    content: str = Field(..., min_length=1)

    # Link to entities (polymorphic)
    entity_type: str = Field(..., max_length=50)  # 'lead', 'contact', 'deal', 'call'
    entity_id: UUID


class NoteCreateRequest(NoteBase):
    """Create note request"""
    pass


class NoteUpdateRequest(BaseModel):
    """Update note request"""
    content: Optional[str] = Field(None, min_length=1)


class NoteResponse(NoteBase):
    """Note response"""
    id: UUID
    company_id: UUID
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    # Related info
    created_by_name: Optional[str] = None

    class Config:
        from_attributes = True


# ===== Common Schemas =====

class PaginatedResponse(BaseModel):
    """Paginated list response"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class BulkDeleteRequest(BaseModel):
    """Bulk delete request"""
    ids: List[UUID] = Field(..., min_items=1, max_items=100)
    hard: bool = False


class ExportRequest(BaseModel):
    """Export request"""
    format: str = Field("csv", description="csv, excel, pdf")
    filters: Optional[Dict[str, Any]] = None
