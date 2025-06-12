from sqlalchemy import Column, Uuid, String
from sqlalchemy.orm import Mapped

from db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = Column(Uuid(as_uuid=True), primary_key=True)
    first_name: Mapped[str] = Column(String(225))
    last_name: Mapped[str] = Column(String(225), nullable=True)
