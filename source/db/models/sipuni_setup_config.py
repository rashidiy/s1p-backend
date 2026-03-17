"""
SipuniSetupConfig model — Per-company Sipuni setup state tracking
"""

from sqlalchemy import Column, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
from sqlalchemy.sql import func

from db.base import Base
from db.mixins.object_manager import ObjectManagerMixin


class SipuniSetupConfig(Base, ObjectManagerMixin):
    """
    Tracks the state of Sipuni one-click setup per company.

    Does NOT store credentials — those go in Company.provider_config.
    This model only tracks setup status and method.
    """

    __tablename__ = "sipuni_setup_configs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Setup state
    setup_status = Column(
        String(20),
        server_default=text("'not_started'"),
        nullable=False
    )  # not_started | setting_up | ready | failed

    setup_error = Column(Text, nullable=True)

    setup_method = Column(String(20), nullable=True)  # auto | manual

    # Which services were enabled during setup
    services_enabled = Column(JSONB, nullable=True)  # {"stream": true, "callback": true}

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
    company = relationship("Company", backref="sipuni_setup_config")

    def __repr__(self):
        return f"<SipuniSetupConfig(company_id={self.company_id}, status={self.setup_status})>"
