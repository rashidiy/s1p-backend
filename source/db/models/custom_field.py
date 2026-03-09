"""
CustomFieldDefinition model - Typed custom field definitions per entity type
"""

from sqlalchemy import (
    Column, DateTime, String, Boolean, Integer, ForeignKey,
    Enum as SQLEnum, Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin
from db.models.enums import CustomFieldTypeEnum


class CustomFieldDefinition(Base, ObjectManagerMixin):
    """
    Custom field definition - defines a typed custom field for an entity type.

    Each company can define up to 20 custom fields per entity type.
    Field types: text, number, dropdown, date, boolean.
    Dropdown fields store their allowed choices in the `options` JSONB column.
    """

    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "entity_type", "field_name",
            name="uq_company_entity_field_name",
        ),
        Index("idx_cfd_company_id", "company_id"),
        Index("idx_cfd_company_entity", "company_id", "entity_type"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Multi-tenant: every definition belongs to a company
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which entity this field applies to
    entity_type = Column(
        String(20),
        nullable=False,
    )  # "contact" | "lead" | "deal" | "task"

    # Field metadata
    field_name = Column(String(100), nullable=False)
    field_type = Column(
        SQLEnum(
            CustomFieldTypeEnum,
            name="custom_field_type_enum",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
    )
    options = Column(JSONB, nullable=True)  # For dropdown: ["option1", "option2", ...]
    is_required = Column(Boolean, nullable=False, server_default=text("false"))
    sort_order = Column(Integer, nullable=False, server_default=text("0"))

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="custom_field_definitions")

    def __repr__(self):
        return (
            f"<CustomFieldDefinition(id={self.id}, entity={self.entity_type}, "
            f"name='{self.field_name}', type='{self.field_type}')>"
        )
