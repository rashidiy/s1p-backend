"""
Permission group schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class PermissionGroupCreateRequest(BaseModel):
    """Create a custom permission group"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: List[str] = Field(..., description="List of permission strings")


class PermissionGroupUpdateRequest(BaseModel):
    """Update a permission group"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class PermissionGroupResponse(BaseModel):
    """Permission group response"""
    id: UUID
    company_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    permissions: List[str]
    is_system: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PermissionGroupListResponse(BaseModel):
    """Permission group list response"""
    groups: List[PermissionGroupResponse]
    total: int
