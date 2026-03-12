"""
Telegram Auth Challenge model — tracks login/register challenge state
"""

from typing import Optional
import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB

from db import Base, ObjectManagerMixin


class TelegramAuthChallenge(Base, ObjectManagerMixin):
    """
    Tracks a Telegram-based auth challenge (login or register).

    For login:
      1. Frontend creates challenge (pending)
      2. User opens deep link, bot sends OTP (otp_sent)
      3. User enters OTP on frontend, backend verifies (used)

    For register:
      1. User sends /register to bot, challenge created
      2. User opens web link, enters invite token
      3. Backend creates user account (used)

    ID is a short URL-safe string (not UUID) for use in deep links.
    """

    __tablename__ = "telegram_auth_challenges"
    __table_args__ = (
        Index('idx_tac_company_id', 'company_id'),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )

    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,  # NULL for register challenges (resolved from invite token)
    )

    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    otp_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )

    purpose: Mapped[str] = mapped_column(
        String(10), nullable=False,
    )

    expires_at = Column(DateTime(timezone=True), nullable=False)

    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
    )

    used: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
    )

    telegram_data = Column(JSONB, nullable=True)

    invite_token_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invite_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company")
    user = relationship("User")
    invite_token = relationship("InviteToken")

    def __repr__(self):
        return f"<TelegramAuthChallenge(id={self.id}, purpose='{self.purpose}')>"
