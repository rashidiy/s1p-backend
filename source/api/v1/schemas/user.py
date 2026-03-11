"""
User management schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

from api.v1.schemas.validators import PasswordValidator
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


class UserBase(BaseModel):
    """Base user schema"""
    email: Optional[EmailStr] = None
    first_name: str = Field(..., min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


class UserInviteRequest(UserBase):
    """Admin invites operator via email"""
    email: EmailStr  # Required for email-based invite (overrides Optional in UserBase)
    role: str = Field(default="company_operator", description="Role: company_admin or company_operator")
    permissions: Optional[List[str]] = Field(default_factory=list, description="Custom permissions")
    permission_group_id: Optional[UUID] = Field(None, description="Permission group to assign")

    @field_validator("permissions")
    @classmethod
    def check_permissions(cls, v):
        if v:
            return _validate_permissions(v)
        return v


class UserCreateRequest(PasswordValidator, UserBase):
    """Create user with password (internal use)"""
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(default="company_operator")
    permissions: Optional[List[str]] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    """Update user information"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    is_suspended: Optional[bool] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    permission_group_id: Optional[UUID] = Field(None, description="Permission group to assign")

    @field_validator("permissions")
    @classmethod
    def check_permissions(cls, v):
        if v is not None:
            return _validate_permissions(v)
        return v


class PasswordChangeRequest(PasswordValidator, BaseModel):
    """Change password request"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordResetRequest(PasswordValidator, BaseModel):
    """Reset password (for temporary passwords)"""
    email: EmailStr
    temporary_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class ProfileUpdateRequest(BaseModel):
    """Update own profile (non-admin fields only)"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)


class UserResponse(UserBase):
    """User response"""
    id: UUID
    company_id: Optional[UUID]
    role: str
    permissions: List[str]
    permission_group_id: Optional[UUID] = None
    is_active: bool
    is_suspended: bool
    email_verified: bool
    language: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserDetailResponse(UserResponse):
    """Detailed user response with stats"""
    total_calls: Optional[int] = 0
    total_leads: Optional[int] = 0
    total_deals: Optional[int] = 0
    total_tasks: Optional[int] = 0

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Paginated user list"""
    users: List[UserResponse]
    total: int
    page: int
    page_size: int
