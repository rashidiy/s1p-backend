"""
Owner schemas for API requests and responses
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class SipuniConfigSchema(BaseModel):
    """Sipuni provider configuration"""
    cabinet_id: str = Field(..., min_length=1, description="Sipuni cabinet ID")
    security_key: str = Field(..., min_length=1, description="Sipuni security key")
    token: Optional[str] = Field(None, description="Webhook validation token")


class BinotelConfigSchema(BaseModel):
    """Binotel provider configuration"""
    cabinet_id: str = Field(..., min_length=1, description="Binotel API key (cabinet ID)")
    security_key: str = Field(..., min_length=1, description="Binotel API secret")
    company_number: Optional[str] = Field(None, description="Default PBX number")


class OwnerBase(BaseModel):
    """Base owner schema"""
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


class OwnerResponse(OwnerBase):
    """Owner response"""
    id: UUID
    is_active: bool
    email_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class OwnerWithCredentials(OwnerResponse):
    """Owner response with JWT credentials"""
    must_change_password: bool = False
    credentials: dict  # {access: str, refresh: str}

    class Config:
        from_attributes = True


class CompanyCreateRequest(BaseModel):
    """Create company request"""
    name: str = Field(..., min_length=1, max_length=255)
    subdomain: Optional[str] = Field(None, min_length=1, max_length=100, description="Company subdomain (auto-generated if not provided)")
    provider_type: str = Field(..., description="Provider: sipuni or binotel")
    provider_config: Optional[dict] = Field(default_factory=dict, description="Provider-specific configuration (optional — can connect later)")
    sipuni_login: Optional[str] = Field(None, description="Sipuni account email/phone for auto-setup")
    sipuni_password: Optional[str] = Field(None, description="Sipuni account password for auto-setup")
    settings: Optional[dict] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_provider_config(self):
        provider = self.provider_type.lower()
        config = self.provider_config or {}

        if provider not in ('sipuni', 'binotel'):
            raise ValueError(f"Invalid provider type: {provider}. Must be 'sipuni' or 'binotel'")

        # If provider_config has credentials, validate them
        if config.get('cabinet_id') or config.get('security_key'):
            if provider == 'sipuni':
                validated = SipuniConfigSchema(**config)
            elif provider == 'binotel':
                validated = BinotelConfigSchema(**config)
            self.provider_config = validated.model_dump(exclude_none=True)
        else:
            self.provider_config = {}

        # Sipuni login/password must be provided together
        if bool(self.sipuni_login) != bool(self.sipuni_password):
            raise ValueError("Both sipuni_login and sipuni_password must be provided together")

        return self

    class Config:
        json_schema_extra = {
            "example": {
                "name": "My Company LLC",
                "subdomain": "mycompany",
                "provider_type": "sipuni",
                "provider_config": {
                    "cabinet_id": "12345",
                    "security_key": "your-secret-key"
                },
                "settings": {
                    "timezone": "Asia/Tashkent",
                    "language": "ru"
                }
            }
        }


class InviteAdminRequest(BaseModel):
    """Owner invites a company admin via Telegram invite token flow"""
    first_name: str = Field(..., min_length=1, max_length=225)
    last_name: str | None = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


class InviteAdminResponse(BaseModel):
    """Response after admin invitation token is created"""
    invite_token: str
    company_name: str
    expires_at: datetime
    role: str
    first_name: str
    phone: Optional[str] = None


class CompanyUpdateRequest(BaseModel):
    """Update company request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class CompanyResponse(BaseModel):
    """Company response"""
    id: UUID
    name: str
    subdomain: str
    provider_type: str
    is_active: bool
    webhook_url: Optional[str] = None  # Computed field
    users_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CompanyDetailResponse(CompanyResponse):
    """Detailed company response with config"""
    provider_config: dict
    settings: Optional[dict] = None
    webhook_token: Optional[str] = None

    class Config:
        from_attributes = True
