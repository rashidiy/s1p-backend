"""
Owner model - Master account that can create multiple companies
"""

from sqlalchemy import Boolean, Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


class Owner(Base):
    """
    Owner model - Platform-level master account

    One Owner can create and manage multiple Companies.
    Owners have full access to all their companies.
    """

    __tablename__ = "owners"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()")
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Personal info
    first_name = Column(String(225))
    last_name = Column(String(225))
    phone = Column(String(50))

    # Status flags
    is_active = Column(Boolean, default=False, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    companies = relationship(
        "Company",
        back_populates="owner",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Owner(id={self.id}, email='{self.email}')>"

    @property
    def full_name(self):
        """Get full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.email
