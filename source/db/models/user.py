import uuid
from typing import List

from sqlalchemy import Uuid, String, Boolean
from sqlalchemy.orm import Mapped, relationship, mapped_column

from db import Base, ObjectManagerMixin, AuthenticationManagerMixin


class User(Base, ObjectManagerMixin, AuthenticationManagerMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), default=uuid.uuid4, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(225), nullable=False)
    last_name: Mapped[str] = mapped_column(String(225))
    email: Mapped[str] = mapped_column(String(225), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(225), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)

    sipuni_integrations: Mapped[List["Sipuni"]] = relationship('Sipuni', back_populates='user')
