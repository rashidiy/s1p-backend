"""
CallEvent model - Unified call tracking for all providers
"""

from sqlalchemy import (
    Boolean, Column, DateTime, String, Integer, BigInteger,
    Text, ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from source.db.base import Base
from source.db.models.enums import CallStatusEnum, ProviderEnum, CallDirectionEnum


class CallEvent(Base):
    """
    Unified Call Event model for all telephony providers

    Stores call data from both Sipuni and Binotel in a unified format.
    Provider-specific data is normalized to common fields.
    """

    __tablename__ = "call_events"
    __table_args__ = (
        UniqueConstraint(
            'company_id', 'provider_type', 'provider_call_id',
            name='uq_company_provider_call'
        ),
        Index('idx_call_events_company_id', 'company_id'),
        Index('idx_call_events_operator_id', 'operator_id'),
        Index('idx_call_events_contact_id', 'contact_id'),
        Index('idx_call_events_lead_id', 'lead_id'),
        Index('idx_call_events_phone_1', 'phone_1'),
        Index('idx_call_events_phone_2', 'phone_2'),
        Index('idx_call_events_created_at', 'created_at'),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    # Company relationship
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Provider info
    provider_type = Column(
        SQLEnum(ProviderEnum, name="provider_enum"),
        nullable=False
    )
    provider_call_id = Column(String(255), nullable=False)  # Sipuni: call_id, Binotel: generalCallID

    # Call participants
    phone_1 = Column(String(50))  # Caller/External number
    phone_2 = Column(String(50))  # Receiver/Internal number

    # Operator (user who handled the call)
    operator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Call metadata
    direction = Column(
        SQLEnum(CallDirectionEnum, name="call_direction_enum"),
        nullable=True
    )
    state = Column(
        SQLEnum(CallStatusEnum, name="call_status_enum"),
        nullable=True
    )
    attempts = Column(Integer, default=1)
    waiting_sec = Column(Integer)  # Time waiting before answer
    billing_sec = Column(Integer)  # Call duration after answer

    # Recording
    record_url = Column(Text)

    # Timestamps (Unix timestamps from providers)
    call_start_timestamp = Column(BigInteger)
    call_end_timestamp = Column(BigInteger)

    # CRM Integration
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True
    )
    lead_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True
    )

    # UTM tracking for marketing attribution
    utm_source = Column(String(255))
    utm_medium = Column(String(255))
    utm_campaign = Column(String(255))

    # Additional metadata from providers
    company_number = Column(String(50))  # Binotel: pbxNumber
    order_id = Column(String(255))  # External order/ticket ID

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="call_events")
    operator = relationship("User", back_populates="call_events")
    contact = relationship("Contact", back_populates="calls")
    lead = relationship("Lead", back_populates="calls")

    def __repr__(self):
        return (
            f"<CallEvent(id={self.id}, provider='{self.provider_type}', "
            f"phone_1='{self.phone_1}', state='{self.state}')>"
        )

    @property
    def duration_sec(self):
        """Get call duration in seconds"""
        return self.billing_sec or 0

    @property
    def is_answered(self):
        """Check if call was answered"""
        return self.state == CallStatusEnum.ANSWER

    @property
    def is_missed(self):
        """Check if call was missed"""
        return self.state in [
            CallStatusEnum.NOANSWER,
            CallStatusEnum.BUSY,
            CallStatusEnum.CANCEL
        ]
