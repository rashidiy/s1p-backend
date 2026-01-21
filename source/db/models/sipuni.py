import uuid
from typing import List

from sqlalchemy import Integer, String, UUID, ForeignKey, UniqueConstraint, BigInteger, Uuid, Enum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import mapped_column, Mapped, relationship

from db import Base, ObjectManagerMixin
from db.models.enums import CallStatusEnum


class Sipuni(Base, ObjectManagerMixin):
    __tablename__ = 'sipuni'

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), default=uuid.uuid4, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cabinet_id: Mapped[str] = mapped_column(String(25), nullable=False)
    security_key: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    partner_name: Mapped[str] = mapped_column(String(255))
    partner_contact: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(String(1024))

    user: Mapped['User'] = relationship("User", back_populates='sipuni_integrations')
    call_events: Mapped[List['SipuniCallEvent']] = relationship("SipuniCallEvent", back_populates='sipuni')

    __table_args__ = (UniqueConstraint('user_id', 'cabinet_id'),)


class SipuniCallEvent(Base, ObjectManagerMixin):
    """Legacy Sipuni call event model - kept for backward compatibility"""
    __tablename__ = 'sipuni_call_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[str] = mapped_column(String(255), unique=True)
    call_start_timestamp = mapped_column(BigInteger)
    call_end_timestamp = mapped_column(BigInteger, nullable=True)
    sipuni_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('sipuni.id'))
    pbxdstnum: Mapped[str] = mapped_column(String(255))
    dst_type: Mapped[str] = mapped_column(String(1))
    src_num: Mapped[str] = mapped_column(String(255))
    src_type: Mapped[str] = mapped_column(String(1))
    last_called: Mapped[str] = mapped_column(ARRAY(String(255)), nullable=True)
    transfer_from: Mapped[str] = mapped_column(String(255), nullable=True)
    tree_number: Mapped[str] = mapped_column(String(255), nullable=True)
    record_link: Mapped[str] = mapped_column(String(2048), nullable=True)
    timestamp = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Enum(CallStatusEnum))

    sipuni: Mapped['Sipuni'] = relationship("Sipuni", back_populates='call_events')


# Alias for backward compatibility
LegacySipuniCallEvent = SipuniCallEvent
