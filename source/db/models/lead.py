"""
Lead model - Sales leads/opportunities
"""

from sqlalchemy import (
    Column, DateTime, String, Text, Numeric, ForeignKey, Index, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin
from db.models.enums import LeadStatusEnum, PipelineStageEnum


class Lead(Base, ObjectManagerMixin):
    """
    Lead model - Sales lead/opportunity

    Represents potential customers in the sales pipeline.
    Can be linked to contacts and eventually converted to deals.
    """

    __tablename__ = "leads"
    __table_args__ = (
        Index('idx_leads_company_id', 'company_id'),
        Index('idx_leads_company_active', 'company_id', 'deleted_at'),
        Index('idx_leads_company_status', 'company_id', 'status', 'deleted_at'),
        Index('idx_leads_contact_id', 'contact_id'),
        Index('idx_leads_assigned_to', 'assigned_to'),
        Index('idx_leads_status', 'status'),
        Index('idx_leads_pipeline_stage', 'pipeline_stage'),
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

    # Contact relationship
    contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Lead info
    title = Column(String(255), nullable=False)
    description = Column(Text)
    source = Column(String(100))  # website, referral, call, campaign, social
    status = Column(
        SQLEnum(LeadStatusEnum, name="lead_status_enum"),
        nullable=False,
        default=LeadStatusEnum.NEW
    )
    pipeline_stage = Column(
        SQLEnum(PipelineStageEnum, name="pipeline_stage_enum"),
        nullable=False,
        default=PipelineStageEnum.NEW
    )

    # Value estimation
    estimated_value = Column(Numeric(15, 2))
    currency = Column(String(10), default="USD")

    # Assignment
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Creator tracking
    created_by = Column(
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
    company = relationship("Company", back_populates="leads")
    contact = relationship("Contact", back_populates="leads")
    assignee = relationship("User", foreign_keys=[assigned_to], back_populates="assigned_leads")

    deals = relationship("Deal", back_populates="lead")
    calls = relationship("CallEvent", back_populates="lead")
    notes = relationship("Note", primaryjoin="and_(Note.entity_type=='lead', Note.entity_id==Lead.id)", foreign_keys="Note.entity_id", viewonly=True)

    def __repr__(self):
        return f"<Lead(id={self.id}, title='{self.title}', status='{self.status}')>"

    def convert_to_deal(self):
        """
        Mark lead as converted

        Call this when creating a deal from a lead
        """
        self.status = LeadStatusEnum.CONVERTED
        self.pipeline_stage = PipelineStageEnum.WON
