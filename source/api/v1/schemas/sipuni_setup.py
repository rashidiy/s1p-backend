"""
Sipuni setup schemas
"""

from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class SipuniSetupRequest(BaseModel):
    """Automated setup — email + password for Sipuni dashboard."""
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class SipuniManualSetupRequest(BaseModel):
    """Manual setup — admin provides credentials directly."""
    cabinet_id: str = Field(min_length=1, max_length=50)
    security_key: str = Field(min_length=1, max_length=256)


class SipuniSetupStatusResponse(BaseModel):
    """Setup status response (used by multiple endpoints)."""
    setup_status: str  # not_started | setting_up | ready | failed
    setup_error: Optional[str] = None
    setup_method: Optional[str] = None  # auto | manual
    is_connected: bool = False
    cabinet_id: Optional[str] = None
    webhook_url: Optional[str] = None


class SipuniConfigResponse(BaseModel):
    """Full Sipuni configuration response."""
    is_connected: bool
    cabinet_id: Optional[str] = None
    security_key_masked: Optional[str] = None
    webhook_url: Optional[str] = None
    setup_status: str = "not_started"
    setup_method: Optional[str] = None
    services_enabled: Optional[dict] = None
