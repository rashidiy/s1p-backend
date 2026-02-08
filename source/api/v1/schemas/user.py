"""
User management schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from api.v1.schemas.validators import PasswordValidator


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


class UserInviteRequest(UserBase):
    """Admin invites operator via email"""
    role: str = Field(default="company_operator", description="Role: company_admin or company_operator")
    permissions: Optional[List[str]] = Field(default_factory=list, description="Custom permissions")


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


class PasswordChangeRequest(PasswordValidator, BaseModel):
    """Change password request"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordResetRequest(PasswordValidator, BaseModel):
    """Reset password (for temporary passwords)"""
    email: EmailStr
    temporary_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class UserResponse(UserBase):
    """User response"""
    id: UUID
    company_id: Optional[UUID]
    role: str
    permissions: List[str]
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
