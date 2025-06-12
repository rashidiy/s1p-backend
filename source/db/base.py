from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from core.config import DatabaseConfig


class AsyncDatabaseSession:
    _engine = create_async_engine(DatabaseConfig.url(), future=True, echo=True)
    _session_factory = sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)

    async def __call__(self) -> AsyncSession:
        async with self._session_factory() as _session:
            print(type(session))
            yield _session


session = AsyncDatabaseSession()
Base = declarative_base()
print(DatabaseConfig.url())
