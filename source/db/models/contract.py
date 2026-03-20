"""
Contract model - Service agreement between Owner and Company
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Integer, Numeric, String, Text,
    ForeignKey, Index, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db import Base, ObjectManagerMixin
from db.models.enums import ContractStatusEnum, BillingPeriodEnum, PaymentStatusEnum


class Contract(Base, ObjectManagerMixin):
    """
    Contract model - Defines resource limits, pricing, and billing for a company.

    Each company can have one active contract at a time.
    Owners create and manage contracts; Company Admins can view status.
    """

    __tablename__ = "contracts"
    __table_args__ = (
        Index("idx_contracts_company_id", "company_id"),
        Index("idx_contracts_owner_id", "owner_id"),
        Index("idx_contracts_status", "status"),
        Index("idx_contracts_end_date", "end_date"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    # Ownership
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Contract info
    name = Column(String(255), nullable=False)

    # Resource limits
    max_admins = Column(Integer, nullable=False, default=1)
    max_managers = Column(Integer, nullable=False, default=5)
    max_operators = Column(Integer, nullable=False, default=10)
    max_storage_gb = Column(Integer, nullable=False, default=10)

    # Pricing
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    billing_period = Column(
        SQLEnum(BillingPeriodEnum, name="billing_period_enum", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BillingPeriodEnum.MONTHLY
    )

    # Status
    status = Column(
        SQLEnum(ContractStatusEnum, name="contract_status_enum", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ContractStatusEnum.ACTIVE
    )
    payment_status = Column(
        SQLEnum(PaymentStatusEnum, name="payment_status_enum", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=PaymentStatusEnum.PAID
    )

    # Dates
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    next_payment_date = Column(Date, nullable=True)
    grace_period_days = Column(Integer, nullable=False, default=30)

    # Flags
    is_active = Column(Boolean, default=True, nullable=False)
    auto_renew = Column(Boolean, default=False, nullable=False)

    # Extra
    notes = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True, server_default=text("'{}'::jsonb"))

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    owner = relationship("Owner", back_populates="contracts")
    company = relationship("Company", back_populates="contracts")

    def __repr__(self):
        return f"<Contract(id={self.id}, company_id={self.company_id}, status='{self.status}')>"

    @property
    def allows_access(self) -> bool:
        """True if contract status permits company access"""
        return self.status in (
            ContractStatusEnum.ACTIVE,
            ContractStatusEnum.WARNING,
            ContractStatusEnum.GRACE_PERIOD,
        )
