"""
Outbound Webhook models — endpoint configuration and delivery tracking
"""

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, Text,
    ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class WebhookEndpoint(Base, ObjectManagerMixin):
    """
    Outbound webhook endpoint configuration

    Companies configure URLs to receive event notifications.
    Each endpoint subscribes to specific event types.
    """

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index('idx_webhook_endpoints_company_id', 'company_id'),
        Index('idx_webhook_endpoints_active', 'is_active'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    url = Column(String(2048), nullable=False)
    events = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    secret = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="webhook_endpoints")
    deliveries = relationship(
        "WebhookDelivery",
        back_populates="endpoint",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<WebhookEndpoint(id={self.id}, url='{self.url}', active={self.is_active})>"


class WebhookDelivery(Base, ObjectManagerMixin):
    """
    Webhook delivery attempt log

    Tracks every delivery attempt with status, response, and retry info.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index('idx_webhook_deliveries_endpoint_id', 'endpoint_id'),
        Index('idx_webhook_deliveries_status', 'status'),
        Index('idx_webhook_deliveries_created_at', 'created_at'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    endpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, success, failed
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")

    def __repr__(self):
        return (
            f"<WebhookDelivery(id={self.id}, event='{self.event_type}', "
            f"status='{self.status}', attempts={self.attempts})>"
        )
