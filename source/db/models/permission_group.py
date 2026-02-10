"""
PermissionGroup model - Reusable permission sets for users
"""

import uuid
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, String, Text, ForeignKey,
    Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, relationship, mapped_column
from sqlalchemy.sql import func

from db import Base, ObjectManagerMixin


class PermissionGroup(Base, ObjectManagerMixin):
    """
    PermissionGroup model - Named, reusable permission sets

    System groups (is_system=True, company_id=NULL) are shared across all companies.
    Custom groups belong to a specific company.
    """

    __tablename__ = "permission_groups"
    __table_args__ = (
        UniqueConstraint('company_id', 'name', name='uq_permission_group_company_name'),
        Index('idx_permission_groups_company_id', 'company_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        primary_key=True
    )

    # Company relationship (NULL for system groups)
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    permissions = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb")
    )

    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

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
    company = relationship("Company", back_populates="permission_groups")
    users = relationship("User", back_populates="permission_group")

    def __repr__(self):
        return f"<PermissionGroup(id={self.id}, name='{self.name}', is_system={self.is_system})>"
