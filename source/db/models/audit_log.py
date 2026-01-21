"""
AuditLog model - Audit trail for all changes
"""

from sqlalchemy import (
    Column, DateTime, String, Text, ForeignKey, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from source.db.base import Base


class AuditLog(Base):
    """
    AuditLog model - Audit trail for compliance and tracking

    Records all state-changing operations (create, update, delete).
    Stores before/after snapshots for rollback and analysis.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index('idx_audit_logs_company_id', 'company_id'),
        Index('idx_audit_logs_user_id', 'user_id'),
        Index('idx_audit_logs_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_logs_created_at', 'created_at'),
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
        nullable=True,  # Nullable for platform-level actions
        index=True
    )

    # User who performed the action
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Action info
    action = Column(String(50), nullable=False)  # 'create', 'update', 'delete', 'login'
    entity_type = Column(String(50))  # 'lead', 'contact', 'user', 'company'
    entity_id = Column(UUID(as_uuid=True))

    # Changes snapshot
    before = Column(JSONB)  # State before change
    after = Column(JSONB)   # State after change

    # Request metadata
    ip_address = Column(String(50))
    user_agent = Column(Text)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"entity_type='{self.entity_type}', user_id='{self.user_id}')>"
        )
