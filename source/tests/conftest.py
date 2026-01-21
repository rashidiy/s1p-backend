import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing app modules
os.environ.setdefault('POSTGRES_HOST', 'localhost')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('POSTGRES_DB', 'test_sip')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
os.environ.setdefault('JWT_SINGING_KEY', 'test-secret-key-for-jwt-signing')
os.environ.setdefault('JWT_ALGORITHM', 'HS256')
os.environ.setdefault('ALLOWED_IPS', '127.0.0.1;testclient')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', '1234567890:ABCdefGHIjklMNOpqrsTUVwxyz')

from db.base import Base, get_session
from db.models import User, Sipuni
from db.models.sipuni import CallEvent
from db.models.enums import CallStatusEnum
from main import app
from utils.managers import JWTManager, PasswordManager


# Test database URL - using SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session_factory = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session


@pytest.fixture(scope="function")
async def client(test_session) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with overridden database session."""

    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(test_session) -> User:
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash=PasswordManager.hash("testpassword123"),
        is_active=False,
        is_suspended=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
async def active_user(test_session) -> User:
    """Create an active test user."""
    user = User(
        id=uuid.uuid4(),
        first_name="Active",
        last_name="User",
        email="active@example.com",
        password_hash=PasswordManager.hash("testpassword123"),
        is_active=True,
        is_suspended=False,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(test_user) -> dict:
    """Generate authentication headers for test user."""
    credentials = JWTManager.generate_credentials(test_user.id)
    return {"Authorization": f"Bearer {credentials['access']}"}


@pytest.fixture
async def active_auth_headers(active_user) -> dict:
    """Generate authentication headers for active test user."""
    credentials = JWTManager.generate_credentials(active_user.id)
    return {"Authorization": f"Bearer {credentials['access']}"}


@pytest.fixture
async def test_sipuni(test_session, test_user) -> Sipuni:
    """Create a test Sipuni integration."""
    sipuni = Sipuni(
        id=uuid.uuid4(),
        company_name="Test Company",
        cabinet_id="12345",
        security_key="test-security-key",
        user_id=test_user.id,
        token="12345:" + "a" * 58,  # 64 characters total
        partner_name="Test Partner",
        partner_contact="partner@example.com",
        comment="Test comment",
    )
    test_session.add(sipuni)
    await test_session.commit()
    await test_session.refresh(sipuni)
    return sipuni


@pytest.fixture
async def test_call_events(test_session, test_sipuni) -> list[CallEvent]:
    """Create test call events."""
    events = []
    base_time = datetime.now(timezone.utc)

    for i in range(5):
        event = CallEvent(
            call_id=f"call-{uuid.uuid4()}",
            sipuni_id=test_sipuni.id,
            pbxdstnum="100",
            dst_type="1",
            src_num="998901234567",
            src_type="1" if i % 2 == 0 else "2",  # Alternating external/internal
            operator=f"operator{i % 3}",
            status=CallStatusEnum.ANSWER if i < 3 else CallStatusEnum.NOANSWER,
            call_start=base_time - timedelta(minutes=30 - i * 5),
            call_end=base_time - timedelta(minutes=25 - i * 5),
        )
        test_session.add(event)
        events.append(event)

    await test_session.commit()
    for event in events:
        await test_session.refresh(event)
    return events


@pytest.fixture
def mock_sipuni_api():
    """Mock the Sipuni API simulator."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"success": True, "call_id": "test-call-123"}
    mock_response.status_code = 200

    return AsyncMock(return_value=mock_response)
