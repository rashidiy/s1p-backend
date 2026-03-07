"""
Deal model - Sales deals/opportunities
"""

from sqlalchemy import (
    Column, DateTime, String, Text, Numeric, Date, Integer,
    ForeignKey, Index, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin
from db.models.enums import DealStageEnum


class Deal(Base, ObjectManagerMixin):
    """
    Deal model - Active sales opportunity

    Represents qualified leads that are in active sales negotiation.
    Tracks deal value, stage, and closure probability.
    """

    __tablename__ = "deals"
    __table_args__ = (
        Index('idx_deals_company_id', 'company_id'),
        Index('idx_deals_lead_id', 'lead_id'),
        Index('idx_deals_contact_id', 'contact_id'),
        Index('idx_deals_assigned_to', 'assigned_to'),
        Index('idx_deals_stage', 'stage'),
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

    # Related entities
    lead_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True
    )
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Deal info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="USD")
    stage = Column(
        SQLEnum(DealStageEnum, name="deal_stage_enum"),
        nullable=False,
        default=DealStageEnum.PROSPECTING
    )
    probability = Column(Integer, default=0)  # 0-100 percentage

    # Win/Loss tracking
    win_reason = Column(String, nullable=True)
    loss_reason = Column(String, nullable=True)

    # Dates
    expected_close_date = Column(Date)
    closed_date = Column(Date)

    # Assignment
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadata
    tags = Column(JSONB, server_default=text("'[]'::jsonb"))
    custom_fields = Column(JSONB, server_default=text("'{}'::jsonb"))

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
    company = relationship("Company", back_populates="deals")
    lead = relationship("Lead", back_populates="deals")
    contact = relationship("Contact", back_populates="deals")
    assignee = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_deals")
    calls = relationship("CallEvent", back_populates="deal")

    notes = relationship("Note", primaryjoin="and_(Note.entity_type=='deal', Note.entity_id==Deal.id)", foreign_keys="Note.entity_id", viewonly=True)

    def __repr__(self):
        return f"<Deal(id={self.id}, title='{self.title}', amount={self.amount}, stage='{self.stage}')>"

    @property
    def is_won(self):
        """Check if deal is won"""
        return self.stage == DealStageEnum.CLOSED_WON

    @property
    def is_lost(self):
        """Check if deal is lost"""
        return self.stage == DealStageEnum.CLOSED_LOST

    @property
    def is_closed(self):
        """Check if deal is closed (won or lost)"""
        return self.is_won or self.is_lost
