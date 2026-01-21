"""
Tag model - Tags for categorization
"""

from sqlalchemy import (
    Column, DateTime, String, ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class Tag(Base):
    """
    Tag model - Tags for categorizing entities

    Company-specific tags that can be applied to contacts, leads, deals, etc.
    Stored as a separate entity for management and reusability.
    """

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint('company_id', 'name', name='uq_company_tag_name'),
        Index('idx_tags_company_id', 'company_id'),
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

    # Tag info
    name = Column(String(100), nullable=False)
    color = Column(String(7), default="#3B82F6")  # Hex color code

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="tags")

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}', color='{self.color}')>"
