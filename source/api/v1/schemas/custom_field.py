"""
Schemas for custom field definitions and values
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


VALID_ENTITY_TYPES = {"contact", "lead", "deal", "task", "note"}
VALID_FIELD_TYPES = {"text", "number", "dropdown", "date", "boolean"}


class CustomFieldDefinitionCreate(BaseModel):
    """Create a custom field definition"""
    entity_type: str = Field(..., max_length=50)
    field_name: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(...)
    options: Optional[List[str]] = None
    sort_order: int = Field(0, ge=0)
    is_required: bool = False

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}")
        return v

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        if v not in VALID_FIELD_TYPES:
            raise ValueError(f"field_type must be one of: {', '.join(sorted(VALID_FIELD_TYPES))}")
        return v

    @field_validator("options")
    @classmethod
    def validate_options(cls, v, info):
        if v is not None and len(v) == 0:
            raise ValueError("options list cannot be empty when provided")
        return v


class CustomFieldDefinitionUpdate(BaseModel):
    """Update a custom field definition"""
    field_name: Optional[str] = Field(None, min_length=1, max_length=100)
    options: Optional[List[str]] = None
    sort_order: Optional[int] = Field(None, ge=0)
    is_required: Optional[bool] = None


class CustomFieldDefinitionResponse(BaseModel):
    """Custom field definition response"""
    id: UUID
    company_id: UUID
    entity_type: str
    field_name: str
    field_type: str
    options: Optional[List[str]] = None
    sort_order: int
    is_required: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomFieldReorderRequest(BaseModel):
    """Reorder custom field definitions"""
    field_ids: List[UUID] = Field(..., min_length=1)
