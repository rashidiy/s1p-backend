"""
Telegram authentication schemas — request/response models
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from api.v1.schemas.auth import AuthSchema
from utils.permissions import Permissions

VALID_PERMISSIONS = Permissions.all()


# ── Invite Token Schemas ──────────────────────────────────────────────

class InviteTokenCreateRequest(BaseModel):
    """Admin creates an invite token for a new user"""
    first_name: str = Field(..., min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: str = Field(..., min_length=1, max_length=50)
    role: str = Field(default="company_operator")
    permissions: Optional[List[str]] = Field(default=None)
    permission_group_id: Optional[uuid.UUID] = None

    @field_validator("permissions")
    @classmethod
    def check_permissions(cls, v):
        if v:
            invalid = [p for p in v if p not in VALID_PERMISSIONS]
            if invalid:
                raise ValueError(f"Invalid permissions: {invalid}")
        return v


class InviteTokenCreateResponse(BaseModel):
    """Returned once after creating an invite token (plaintext token)"""
    invite_token: str
    expires_at: datetime
    role: str
    first_name: str
    phone: str


class InviteTokenListItem(BaseModel):
    """Single item in the invite token list"""
    id: uuid.UUID
    role: str
    first_name: str
    last_name: Optional[str] = None
    phone: str
    created_by_name: Optional[str] = None
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime
    status: str  # "pending" | "used" | "expired"

    class Config:
        from_attributes = True


class InviteTokenListResponse(BaseModel):
    """Paginated list of invite tokens"""
    items: List[InviteTokenListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Login Challenge Schemas ───────────────────────────────────────────

class LoginChallengeResponse(BaseModel):
    """Returned when creating a login challenge"""
    challenge_id: str
    deep_link: str
    expires_at: datetime


class ChallengeStatusResponse(BaseModel):
    """Returned when polling challenge status"""
    status: str  # "pending" | "otp_sent" | "expired" | "used"
    expires_at: datetime


# ── OTP Verification Schemas ─────────────────────────────────────────

class VerifyOtpRequest(BaseModel):
    """User submits 6-digit OTP from Telegram"""
    challenge_id: str = Field(..., min_length=1)
    otp: str = Field(..., min_length=6, max_length=6)


# ── Registration Schemas ─────────────────────────────────────────────

class RegisterPrefillResponse(BaseModel):
    """Pre-fill data for registration form from Telegram profile"""
    telegram_first_name: Optional[str] = None
    telegram_last_name: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_avatar_file_id: Optional[str] = None
    invite_phone: Optional[str] = None
    invite_first_name: Optional[str] = None


class TelegramRegisterRequest(BaseModel):
    """User completes registration with invite token"""
    session_id: str = Field(..., min_length=1)
    invite_token: str = Field(..., min_length=1)
    first_name: Optional[str] = Field(None, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)
    skip_avatar: bool = False


# ── Register Challenge Schemas (invite code → Telegram connect) ─────

class RegisterChallengeRequest(BaseModel):
    """Create a registration challenge from an invite code"""
    invite_token: str = Field(..., min_length=1)


class RegisterChallengeResponse(BaseModel):
    """Returned when creating a registration challenge"""
    challenge_id: str
    deep_link: str
    company_name: str
    invite_first_name: Optional[str] = None
    invite_last_name: Optional[str] = None
    invite_phone: Optional[str] = None


class RegisterChallengeStatusResponse(BaseModel):
    """Status of a registration challenge (polling)"""
    status: str  # "pending" | "telegram_connected" | "expired" | "used"
    telegram_first_name: Optional[str] = None
    telegram_last_name: Optional[str] = None
    telegram_username: Optional[str] = None
    has_avatar: bool = False
