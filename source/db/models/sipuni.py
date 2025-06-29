import uuid

from sqlalchemy import Integer, String, UUID, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from db import Base, ObjectManagerMixin


class Sipuni(Base, ObjectManagerMixin):
    __tablename__ = 'sipuni'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cabinet_id: Mapped[str] = mapped_column(String(25), nullable=False)
    security_key: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    partner_name: Mapped[str] = mapped_column(String(255))
    partner_contact: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(String(1024))

    user: Mapped['User'] = relationship("User", back_populates='sipuni_integrations')

    __table_args__ = (UniqueConstraint('user_id', 'cabinet_id'),)
