"""
Invite Token model — stores hashed invite codes for Telegram-based registration
"""

import uuid
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from db import Base, ObjectManagerMixin
from db.models.enums import RoleEnum


class InviteToken(Base, ObjectManagerMixin):
    """
    Invite token for Telegram-based user registration.

    Admin creates an invite token (XXXX-XXXX format).
    The plaintext is shown once; only SHA-256 hash is stored.
    User redeems it during /register flow to create their account.
    """

    __tablename__ = "invite_tokens"
    __table_args__ = (
        Index('idx_invite_tokens_company_id', 'company_id'),
        Index('idx_invite_tokens_token_hash', 'token_hash'),
        Index('idx_invite_tokens_created_by', 'created_by'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        primary_key=True,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    role: Mapped[RoleEnum] = mapped_column(
        SQLEnum(RoleEnum, name="role_enum", create_type=False),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(String(225), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(225), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)

    permissions = Column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    permission_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permission_groups.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    used_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company")
    creator = relationship("User", foreign_keys=[created_by])
    redeemer = relationship("User", foreign_keys=[used_by])

    def __repr__(self):
        return f"<InviteToken(id={self.id}, company_id={self.company_id}, phone='{self.phone}')>"
