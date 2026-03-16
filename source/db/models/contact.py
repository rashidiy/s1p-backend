"""
Contact model - Customer/Client records
"""

from sqlalchemy import (
    Column, DateTime, String, Text, ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class Contact(Base, ObjectManagerMixin):
    """
    Contact model - CRM contact/customer records

    Represents individuals or companies that interact with the business.
    Can be linked to leads, deals, and call events.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        Index('idx_contacts_company_id', 'company_id'),
        Index('idx_contacts_company_active', 'company_id', 'deleted_at'),
        Index('idx_contacts_phone', 'phone'),
        Index('idx_contacts_email', 'email'),
        Index('idx_contacts_assigned_to', 'assigned_to'),
        Index('idx_contacts_created_by', 'created_by'),
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

    # Contact info
    first_name = Column(String(255))
    last_name = Column(String(255))
    company_name = Column(String(255))
    phone = Column(String(50), index=True)
    email = Column(String(255), index=True)

    # Additional fields
    position = Column(String(255))  # Job title
    source = Column(String(100))  # website, call, manual, import, referral
    tags = Column(JSONB, server_default=text("'[]'::jsonb"))
    custom_fields = Column(JSONB, server_default=text("'{}'::jsonb"))

    # Assignment
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

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
    company = relationship("Company", back_populates="contacts")
    creator = relationship("User", foreign_keys=[created_by], back_populates="created_contacts")
    assignee = relationship("User", foreign_keys=[assigned_to])

    leads = relationship("Lead", back_populates="contact")
    deals = relationship("Deal", back_populates="contact")
    calls = relationship("CallEvent", back_populates="contact")
    notes = relationship("Note", primaryjoin="and_(Note.entity_type=='contact', Note.entity_id==Contact.id)", foreign_keys="Note.entity_id", viewonly=True)

    def __repr__(self):
        return f"<Contact(id={self.id}, name='{self.full_name}', phone='{self.phone}')>"

    @property
    def full_name(self):
        """Get full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.company_name or "Unknown"
