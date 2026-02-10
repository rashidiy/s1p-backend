"""
Owner schemas for API requests and responses
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
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
    first_name: str = Field(..., min_length=1, max_length=225)
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
    credentials: dict  # {access: str, refresh: str}

    class Config:
        from_attributes = True


class CompanyCreateRequest(BaseModel):
    """Create company request"""
    name: str = Field(..., min_length=1, max_length=255)
    subdomain: Optional[str] = Field(None, min_length=1, max_length=100, description="Company subdomain (auto-generated if not provided)")
    provider_type: str = Field(..., description="Provider: sipuni or binotel")
    provider_config: dict = Field(..., description="Provider-specific configuration (requires cabinet_id and security_key)")
    settings: Optional[dict] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_provider_config(self):
        provider = self.provider_type.lower()
        config = self.provider_config

        if provider == 'sipuni':
            validated = SipuniConfigSchema(**config)
        elif provider == 'binotel':
            validated = BinotelConfigSchema(**config)
        else:
            raise ValueError(f"Invalid provider type: {provider}. Must be 'sipuni' or 'binotel'")

        self.provider_config = validated.model_dump(exclude_none=True)
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
    """Owner invites a superadmin to a company (gets full admin permissions)"""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=225)
    last_name: Optional[str] = Field(None, max_length=225)
    phone: Optional[str] = Field(None, max_length=50)


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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CompanyDetailResponse(CompanyResponse):
    """Detailed company response with config"""
    provider_config: dict
    settings: Optional[dict] = None
    webhook_token: str

    class Config:
        from_attributes = True
