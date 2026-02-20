from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncAttrs
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column, DeclarativeBase

from core.config import DatabaseConfig


class AsyncDatabaseSession:
    _engine = create_async_engine(DatabaseConfig.url(), future=True, echo=False)
    _session_factory = sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)

    async def __call__(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as _session:
            yield _session


class Base(AsyncAttrs, DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


get_session = AsyncDatabaseSession()
