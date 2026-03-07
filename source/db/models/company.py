"""
Company model - Tenant in multi-tenant architecture
"""

from sqlalchemy import Boolean, Column, DateTime, String, Text, text
from sqlalchemy import ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db import Base, ObjectManagerMixin
from db.models.enums import ProviderEnum


class Company(Base, ObjectManagerMixin):
    """
    Company model - Multi-tenant entity

    Each company:
    - Belongs to one Owner
    - Uses exactly one telephony provider (Sipuni OR Binotel)
    - Has its own users, leads, contacts, calls, etc.
    - Isolated data (all queries filtered by company_id)
    """

    __tablename__ = "companies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    # Owner relationship
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Company info
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True, nullable=False, index=True)

    # Telephony provider
    provider_type = Column(
        SQLEnum(ProviderEnum, name="provider_enum"),
        nullable=False,
        index=True
    )

    # Provider-specific configuration stored as JSON
    # For Sipuni: {cabinet_id, security_key, token}
    # For Binotel: {cabinet_id, security_key, company_number}
    provider_config = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    # Webhook token for receiving provider webhooks
    webhook_token = Column(String(64), unique=True, nullable=True, index=True)

    # Localization
    timezone = Column(String(50), default="Asia/Tashkent")
    locale = Column(String(10), default="ru")

    # Business info
    phone = Column(String(50))
    address = Column(Text)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    owner = relationship("Owner", back_populates="companies")
    users = relationship(
        "User",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    call_events = relationship(
        "CallEvent",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    contacts = relationship(
        "Contact",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    leads = relationship(
        "Lead",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    deals = relationship(
        "Deal",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    tasks = relationship(
        "Task",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    notes = relationship(
        "Note",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    tags = relationship(
        "Tag",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    contracts = relationship(
        "Contract",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "AuditLog",
        back_populates="company",
        cascade="all, delete-orphan"
    )
    permission_groups = relationship(
        "PermissionGroup",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}', provider='{self.provider_type}')>"

    @property
    def is_sipuni(self):
        """Check if company uses Sipuni"""
        return self.provider_type == ProviderEnum.SIPUNI

    @property
    def is_binotel(self):
        """Check if company uses Binotel"""
        return self.provider_type == ProviderEnum.BINOTEL
