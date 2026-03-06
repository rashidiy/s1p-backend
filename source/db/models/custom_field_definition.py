"""
CustomFieldDefinition model - Custom field schema definitions per company/entity
"""

from sqlalchemy import (
    Column, DateTime, String, Integer, Boolean, ForeignKey, Index,
    UniqueConstraint, text
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin
from db.models.enums import CustomFieldTypeEnum


class CustomFieldDefinition(Base, ObjectManagerMixin):
    """
    Custom field definition — describes a custom field for a CRM entity type.

    Each company can define up to 20 custom fields per entity type.
    Values are stored in the entity's custom_fields JSONB column.
    """

    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        Index('idx_cfd_company_id', 'company_id'),
        Index('idx_cfd_entity_type', 'entity_type'),
        Index('idx_cfd_company_entity', 'company_id', 'entity_type'),
        UniqueConstraint(
            'company_id', 'entity_type', 'field_name',
            name='uq_cfd_company_entity_field'
        ),
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

    entity_type = Column(String(50), nullable=False)  # contact, lead, deal, task, note
    field_name = Column(String(100), nullable=False)
    field_type = Column(
        SQLEnum(CustomFieldTypeEnum, name="custom_field_type_enum"),
        nullable=False
    )
    options = Column(JSONB, nullable=True)  # dropdown options list
    sort_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    is_required = Column(Boolean, nullable=False, default=False, server_default=text("false"))

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
    company = relationship("Company")

    def __repr__(self):
        return f"<CustomFieldDefinition(id={self.id}, entity={self.entity_type}, name='{self.field_name}', type='{self.field_type}')>"
