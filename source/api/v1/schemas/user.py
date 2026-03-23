"""
User management schemas
"""

from typing import Optional, List, Dict, Any
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
    sip_extension: Optional[str] = Field(None, max_length=20)
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
    telegram_dm_prefs: Optional[Dict[str, Any]] = Field(
        None,
        description="Telegram DM notification preferences: my_calls, my_leads, assigned_to_me (bool), quiet_hours_start/end (int 0-23)",
    )

    @field_validator("telegram_dm_prefs")
    @classmethod
    def validate_telegram_dm_prefs(cls, v):
        if v is None:
            return v
        allowed_keys = {"my_calls", "my_leads", "assigned_to_me", "quiet_hours_start", "quiet_hours_end"}
        invalid_keys = set(v.keys()) - allowed_keys
        if invalid_keys:
            raise ValueError(f"Invalid keys: {invalid_keys}. Allowed: {sorted(allowed_keys)}")
        for key in ("quiet_hours_start", "quiet_hours_end"):
            if key in v and v[key] is not None:
                if not isinstance(v[key], int) or not (0 <= v[key] <= 23):
                    raise ValueError(f"{key} must be an integer between 0 and 23")
        return v


class UserResponse(UserBase):
    """User response"""
    id: UUID
    company_id: Optional[UUID]
    company_subdomain: Optional[str] = None
    role: str
    permissions: List[str]
    permission_group_id: Optional[UUID] = None
    sip_extension: Optional[str] = None
    is_active: Optional[bool] = True
    is_suspended: Optional[bool] = False
    language: Optional[str] = "ru"
    telegram_user_id: Optional[int] = None
    telegram_username: Optional[str] = None
    telegram_first_name: Optional[str] = None
    telegram_last_name: Optional[str] = None
    telegram_dm_prefs: Optional[Dict[str, Any]] = None
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
