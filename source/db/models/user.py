"""
User model - Company-level user account
"""

import uuid
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, String, Text, ForeignKey,
    Index, UniqueConstraint, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.sql import func

from db import Base, ObjectManagerMixin, AuthenticationManagerMixin
from db.models.enums import RoleEnum


class User(Base, ObjectManagerMixin, AuthenticationManagerMixin):
    """
    User model - Belongs to a Company

    Multi-tenant: All users belong to exactly one company
    Permissions are checked via JWT token
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint('company_id', 'email', name='uq_company_email'),
        Index('idx_users_company_id', 'company_id'),
        Index('idx_users_email', 'email'),
        Index('idx_users_role', 'role'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        primary_key=True
    )

    # Company relationship
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,  # Nullable for owner-level users
        index=True
    )

    # Personal info
    first_name: Mapped[str] = mapped_column(String(225), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(225))
    email: Mapped[str] = mapped_column(String(225), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(225), nullable=False)

    # Role & Permissions
    role: Mapped[RoleEnum] = mapped_column(
        SQLEnum(RoleEnum, name="role_enum"),
        nullable=False,
        default=RoleEnum.COMPANY_OPERATOR
    )
    permissions = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )  # ["leads.read", "calls.write"]

    # Localization
    language: Mapped[str] = mapped_column(String(10), default="ru")

    # Status flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

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
    company = relationship("Company", back_populates="users")

    # CRM relationships
    assigned_leads = relationship("Lead", foreign_keys="Lead.assigned_to", back_populates="assignee")
    assigned_deals = relationship("Deal", foreign_keys="Deal.assigned_to", back_populates="assignee")
    assigned_tasks = relationship("Task", foreign_keys="Task.assigned_to", back_populates="assignee")
    created_tasks = relationship("Task", foreign_keys="Task.created_by", back_populates="creator")
    created_contacts = relationship("Contact", foreign_keys="Contact.created_by", back_populates="creator")
    call_events = relationship("CallEvent", back_populates="operator")
    audit_logs = relationship("AuditLog", back_populates="user")

    # Permission group
    permission_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permission_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    permission_group = relationship("PermissionGroup", back_populates="users")

    # Legacy Sipuni integrations
    sipuni_integrations = relationship("Sipuni", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"

    @property
    def full_name(self):
        """Get full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.email

    def has_permission(self, permission: str) -> bool:
        """
        Check if user has a specific permission

        Effective permissions = group permissions ∪ individual permissions

        Args:
            permission: Permission string (e.g., "leads.read")

        Returns:
            True if user has permission
        """
        if self.role == RoleEnum.OWNER:
            return True  # Owners have all permissions

        effective = set(self.permissions or [])
        if self.permission_group and self.permission_group.permissions:
            effective |= set(self.permission_group.permissions)

        return permission in effective
