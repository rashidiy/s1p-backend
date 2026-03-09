"""
TelegramBotConfig model - Per-company Telegram notification settings
"""

from sqlalchemy import (
    Column, DateTime, String, Boolean, ForeignKey, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class TelegramBotConfig(Base, ObjectManagerMixin):
    """
    Telegram bot configuration per company.

    One shared bot (token in env var), each company configures
    which chat_id receives notifications and which events to send.
    """

    __tablename__ = "telegram_bot_configs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Telegram chat/group ID where notifications are sent
    chat_id = Column(String(100), nullable=False, index=True)

    # Which notifications to send
    # {"call_completed": true, "call_missed": true, "new_lead": true, "deal_stage_change": true}
    notification_filters = Column(
        JSONB,
        nullable=False,
        server_default=text(
            "'{\"call_completed\": true, \"call_missed\": true, "
            "\"new_lead\": true, \"deal_stage_change\": true}'::jsonb"
        )
    )

    enabled = Column(Boolean, default=True, nullable=False)

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
    company = relationship("Company", backref="telegram_config")

    def __repr__(self):
        return f"<TelegramBotConfig(company_id={self.company_id}, chat_id={self.chat_id}, enabled={self.enabled})>"

    def is_event_enabled(self, event_type: str) -> bool:
        """Check if a specific notification event is enabled"""
        if not self.enabled:
            return False
        filters = self.notification_filters or {}
        return filters.get(event_type, False)
