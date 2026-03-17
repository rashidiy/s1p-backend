"""
User management schemas
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

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
    first_name: Optional[str] = Field(None, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


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
    company_subdomain: Optional[str] = None
    role: str
    permissions: List[str]
    permission_group_id: Optional[UUID] = None
    is_active: Optional[bool] = True
    is_suspended: Optional[bool] = False
    language: Optional[str] = "ru"
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    telegram_first_name: Optional[str] = None
    telegram_last_name: Optional[str] = None
    avatar: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode='after')
    def compute_fields(self):
        if self.avatar:
            from core.config import AppConfig
            self.avatar_url = f"{AppConfig.BASE_URL}/media/avatars/{self.avatar}"
        return self


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
    items: List[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
