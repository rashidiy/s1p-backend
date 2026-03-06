"""
TelegramConfig model - Per-company Telegram bot notification settings
"""

from sqlalchemy import (
    Boolean, Column, DateTime, BigInteger,
    ForeignKey, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class TelegramConfig(Base, ObjectManagerMixin):
    """
    Telegram bot configuration per company.

    Maps a company to a Telegram chat_id and stores notification preferences.
    Multi-tenant: one config per company, unique constraint on company_id.
    """

    __tablename__ = "telegram_configs"
    __table_args__ = (
        UniqueConstraint('company_id', name='uq_telegram_config_company'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    # Company relationship (one config per company)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Telegram chat ID — set when company connects via /start command
    chat_id = Column(BigInteger, nullable=True)

    # Master switch
    bot_enabled = Column(Boolean, default=True, nullable=False)

    # Notification preferences
    notify_completed_calls = Column(Boolean, default=True, nullable=False)
    notify_missed_calls = Column(Boolean, default=True, nullable=False)
    notify_new_leads = Column(Boolean, default=True, nullable=False)
    notify_deal_stage_change = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", backref="telegram_config", uselist=False)

    def __repr__(self):
        return (
            f"<TelegramConfig(company_id={self.company_id}, "
            f"chat_id={self.chat_id}, enabled={self.bot_enabled})>"
        )

    @property
    def is_connected(self) -> bool:
        """Check if Telegram chat is connected and bot is enabled."""
        return self.chat_id is not None and self.bot_enabled
