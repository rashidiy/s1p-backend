"""
Note model - Notes and comments
"""

from sqlalchemy import (
    Column, DateTime, String, Text, ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class Note(Base, ObjectManagerMixin):
    """
    Note model - Notes and comments

    Can be attached to any entity (lead, contact, deal, call, etc.)
    Stores free-form text notes for record keeping.
    """

    __tablename__ = "notes"
    __table_args__ = (
        Index('idx_notes_company_id', 'company_id'),
        Index('idx_notes_created_by', 'created_by'),
        Index('idx_notes_entity', 'entity_type', 'entity_id'),
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

    # Note content
    content = Column(Text, nullable=False)

    # Linked entity (polymorphic)
    entity_type = Column(String(50), nullable=False)  # 'lead', 'contact', 'deal', 'call'
    entity_id = Column(String(255), nullable=False)

    # Custom fields
    custom_fields = Column(JSONB, server_default=text("'{}'::jsonb"))

    # Created by
    created_by = Column(
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
    company = relationship("Company", back_populates="notes")
    creator = relationship("User")

    def __repr__(self):
        return f"<Note(id={self.id}, entity_type='{self.entity_type}', entity_id='{self.entity_id}')>"
