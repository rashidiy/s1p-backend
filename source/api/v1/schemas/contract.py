"""
Contract schemas for API requests and responses
"""

from typing import Literal, Optional, List
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field

from db.models.enums import ContractStatusEnum, BillingPeriodEnum, PaymentStatusEnum


class ContractCreateRequest(BaseModel):
    """Create a new contract for a company"""
    company_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    max_admins: int = Field(1, ge=1)
    max_managers: int = Field(5, ge=0)
    max_operators: int = Field(10, ge=0)
    max_storage_gb: int = Field(10, ge=1)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    currency: Literal["USD", "UZS"] = Field("USD", min_length=3, max_length=3)
    billing_period: BillingPeriodEnum = BillingPeriodEnum.MONTHLY
    start_date: date
    end_date: date
    next_payment_date: Optional[date] = None
    grace_period_days: int = Field(30, ge=0)
    auto_renew: bool = False
    notes: Optional[str] = Field(None, max_length=5000)
    metadata_: Optional[dict] = Field(None, alias="metadata")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "company_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Standard Plan",
                "max_admins": 2,
                "max_managers": 5,
                "max_operators": 20,
                "max_storage_gb": 50,
                "price": 99.99,
                "currency": "USD",
                "billing_period": "monthly",
                "start_date": "2025-01-01",
                "end_date": "2025-12-31"
            }
        }


class ContractUpdateRequest(BaseModel):
    """Update an existing contract"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    max_admins: Optional[int] = Field(None, ge=1)
    max_managers: Optional[int] = Field(None, ge=0)
    max_operators: Optional[int] = Field(None, ge=0)
    max_storage_gb: Optional[int] = Field(None, ge=1)
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    currency: Optional[Literal["USD", "UZS"]] = Field(None, min_length=3, max_length=3)
    billing_period: Optional[BillingPeriodEnum] = None
    status: Optional[ContractStatusEnum] = None
    payment_status: Optional[PaymentStatusEnum] = None
    next_payment_date: Optional[date] = None
    grace_period_days: Optional[int] = Field(None, ge=0)
    auto_renew: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)
    metadata_: Optional[dict] = Field(None, alias="metadata")

    class Config:
        populate_by_name = True


class ContractRenewRequest(BaseModel):
    """Renew an existing contract"""
    new_end_date: date
    next_payment_date: Optional[date] = None
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class ContractResponse(BaseModel):
    """Standard contract response"""
    id: UUID
    owner_id: UUID
    company_id: UUID
    name: str
    max_admins: int
    max_managers: int
    max_operators: int
    max_storage_gb: int
    price: Decimal
    currency: str
    billing_period: BillingPeriodEnum
    status: ContractStatusEnum
    payment_status: PaymentStatusEnum
    start_date: date
    end_date: date
    next_payment_date: Optional[date] = None
    grace_period_days: int
    is_active: bool
    auto_renew: bool
    notes: Optional[str] = None
    company_name: Optional[str] = None
    days_until_expiry: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContractDetailResponse(ContractResponse):
    """Detailed contract response with current usage counts"""
    current_admins: int = 0
    current_managers: int = 0
    current_operators: int = 0

    class Config:
        from_attributes = True


class ContractStatusResponse(BaseModel):
    """Simplified contract view for company users"""
    id: UUID
    name: str
    status: ContractStatusEnum
    payment_status: PaymentStatusEnum
    max_admins: int
    max_managers: int
    max_operators: int
    max_storage_gb: int
    current_admins: int = 0
    current_managers: int = 0
    current_operators: int = 0
    start_date: date
    end_date: date
    days_until_expiry: Optional[int] = None
    billing_period: BillingPeriodEnum
    auto_renew: bool
    warnings: List[str] = []

    class Config:
        from_attributes = True
