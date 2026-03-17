"""
Permission group schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from utils.permissions import Permissions

VALID_PERMISSIONS = Permissions.all()


def _validate_permissions(permissions: List[str]) -> List[str]:
    invalid = [p for p in permissions if p not in VALID_PERMISSIONS]
    if invalid:
        raise ValueError(
            f"Invalid permissions: {invalid}. "
            f"Valid permissions: {sorted(VALID_PERMISSIONS)}"
        )
    return permissions


class PermissionGroupCreateRequest(BaseModel):
    """Create a custom permission group"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: List[str] = Field(..., min_length=1, description="List of permission strings")

    @field_validator("permissions")
    @classmethod
    def check_permissions(cls, v):
        return _validate_permissions(v)


class PermissionGroupUpdateRequest(BaseModel):
    """Update a permission group"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: Optional[List[str]] = None

    @field_validator("permissions")
    @classmethod
    def check_permissions(cls, v):
        if v is not None:
            return _validate_permissions(v)
        return v


class PermissionGroupResponse(BaseModel):
    """Permission group response"""
    id: UUID
    company_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    permissions: List[str]
    is_system: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PermissionGroupListResponse(BaseModel):
    """Permission group list response"""
    groups: List[PermissionGroupResponse]
    total: int
