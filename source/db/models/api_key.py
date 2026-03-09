"""
ApiKey model - API keys for public REST API access
"""

from sqlalchemy import (
    Boolean, Column, DateTime, String,
    ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class ApiKey(Base, ObjectManagerMixin):
    """
    API Key model for public API authentication

    Each key belongs to a company. The raw key is shown only once on creation.
    We store a SHA-256 hash for fast lookup and a prefix for user identification.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index('idx_api_keys_key_hash', 'key_hash', unique=True),
        Index('idx_api_keys_company_id', 'company_id'),
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

    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hex
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for display

    name = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    company = relationship("Company", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey(id={self.id}, name='{self.name}', prefix='{self.key_prefix}...')>"
