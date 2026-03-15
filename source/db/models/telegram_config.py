"""
TelegramBotConfig model - Per-company Telegram notification settings
"""

from sqlalchemy import (
    Column, DateTime, Integer, String, Boolean, ForeignKey, Text, text
)
from sqlalchemy.dialects.postgresql import BIGINT, UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


# Topic name → event type mapping
TOPIC_EVENT_MAP = {
    "calls": "call_completed",
    "missed": "call_missed",
    "leads": "new_lead",
    "deals": "deal_stage_change",
    "general": None,
}


class TelegramBotConfig(Base, ObjectManagerMixin):
    """
    Telegram bot configuration per company.

    One shared bot (token in env var), each company configures
    which chat_id receives notifications and which events to send.

    V2 adds: supergroup with topics, automated setup, i18n, recordings,
    daily digest, DM notifications.
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

    # Legacy: simple chat_id for direct messages (kept for backward compat)
    chat_id = Column(String(100), nullable=True, index=True)

    # V2: supergroup with forum topics
    group_chat_id = Column(BIGINT, nullable=True)
    topic_ids = Column(JSONB, nullable=True)  # {"calls": 123, "missed": 124, "leads": 125, "deals": 126, "general": 1}
    invite_link = Column(String(255), nullable=True)
    setup_status = Column(String(20), server_default=text("'not_started'"), nullable=False)  # not_started|creating|ready|failed|manual
    setup_error = Column(Text, nullable=True)
    group_name = Column(String(255), nullable=True)

    # Notification settings
    language = Column(String(10), server_default=text("'ru'"), nullable=False)  # ru|en|uz
    send_recordings = Column(Boolean, server_default=text("'true'"), nullable=False)
    daily_digest = Column(Boolean, server_default=text("'true'"), nullable=False)
    dm_notifications = Column(Boolean, server_default=text("'false'"), nullable=False)
    digest_message_id = Column(Integer, nullable=True)

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

    @property
    def effective_chat_id(self) -> str | None:
        """Returns the group_chat_id (V2) or legacy chat_id, whichever is set."""
        if self.group_chat_id:
            return str(self.group_chat_id)
        return self.chat_id

    def get_topic_thread_id(self, event_type: str | None) -> int | None:
        """Get the message_thread_id for routing a notification to the right topic.
        Returns None if no topics configured (sends to main chat).
        Thread ID 1 (General) is returned as None — Telegram routes to General
        implicitly when no thread_id is specified, and thread_id=1 may fail
        if the General topic is hidden.
        """
        if not self.topic_ids:
            return None
        # Map event_type → topic name
        for topic_name, mapped_event in TOPIC_EVENT_MAP.items():
            if mapped_event == event_type:
                thread_id = self.topic_ids.get(topic_name)
                return thread_id if thread_id and thread_id != 1 else None
        # Fallback to general topic (no thread_id — Telegram uses General implicitly)
        return None
