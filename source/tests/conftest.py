"""
Test configuration and fixtures for SIPtools
"""

import asyncio
import os
import sys
import uuid
from typing import AsyncGenerator, Generator
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

# Add source and project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Use the actual database for testing (PostgreSQL required for JSONB)
TEST_DATABASE_URL = os.environ.get(
    'TEST_DATABASE_URL',
    f"postgresql+asyncpg://{os.environ.get('POSTGRES_USER', 'postgres')}:{os.environ.get('POSTGRES_PASSWORD', 'postgres')}@{os.environ.get('POSTGRES_HOST', 'localhost')}:{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ.get('POSTGRES_DB', 'sip_tools')}_test"
)

# Fallback to main database if test database doesn't exist
MAIN_DATABASE_URL = f"postgresql+asyncpg://{os.environ.get('POSTGRES_USER', 'postgres')}:{os.environ.get('POSTGRES_PASSWORD', 'postgres')}@{os.environ.get('POSTGRES_HOST', 'localhost')}:{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ.get('POSTGRES_DB', 'sip_tools')}"

from db.base import Base
from db.models import Owner, Company, User, Contact, Lead, Deal, Task, Note, CallEvent
from db.models.enums import RoleEnum, ProviderEnum, LeadStatusEnum, DealStageEnum, TaskStatusEnum, TaskPriorityEnum
from utils.managers import PasswordManager, JWTManager


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async engine for tests using the main database."""
    # Use main database for testing (transactions will be rolled back)
    engine = create_async_engine(
        MAIN_DATABASE_URL,
        echo=False
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for tests with transaction rollback."""
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    async with async_session_factory() as session:
        # Use a savepoint approach for test isolation
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(async_engine, db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with overridden dependencies."""
    from main import app
    from db.base import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_owner(db_session: AsyncSession) -> Owner:
    """Create a test owner."""
    owner = Owner(
        id=uuid.uuid4(),
        email=f"owner_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Test",
        last_name="Owner",
        phone="+1234567890",
        is_active=True,
        email_verified=True
    )
    db_session.add(owner)
    await db_session.flush()
    return owner


@pytest_asyncio.fixture
async def test_company(db_session: AsyncSession, test_owner: Owner) -> Company:
    """Create a test company."""
    company = Company(
        id=uuid.uuid4(),
        owner_id=test_owner.id,
        name="Test Company",
        subdomain=f"test_{uuid.uuid4().hex[:8]}",
        provider_type=ProviderEnum.SIPUNI,
        provider_config={"sipuni_user": "test", "sipuni_secret": "secret"},
        webhook_token=str(uuid.uuid4()),
        is_active=True
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_company: Company) -> User:
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        company_id=test_company.id,
        email=f"user_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Test",
        last_name="User",
        phone="+1234567890",
        role=RoleEnum.COMPANY_ADMIN,
        permissions=["*"],
        is_active=True,
        email_verified=True
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_operator(db_session: AsyncSession, test_company: Company) -> User:
    """Create a test operator user."""
    user = User(
        id=uuid.uuid4(),
        company_id=test_company.id,
        email=f"operator_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Test",
        last_name="Operator",
        phone="+1234567891",
        role=RoleEnum.COMPANY_OPERATOR,
        permissions=["leads.read", "contacts.read", "calls.read", "calls.write", "calls.make"],
        is_active=True,
        email_verified=True
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_contact(db_session: AsyncSession, test_company: Company, test_user: User) -> Contact:
    """Create a test contact."""
    contact = Contact(
        id=uuid.uuid4(),
        company_id=test_company.id,
        first_name="John",
        last_name="Doe",
        email=f"john_{uuid.uuid4().hex[:8]}@example.com",
        phone="+1234567890",
        company_name="Acme Corp",
        position="CEO",
        source="website",
        created_by=test_user.id
    )
    db_session.add(contact)
    await db_session.flush()
    return contact


@pytest_asyncio.fixture
async def test_lead(db_session: AsyncSession, test_company: Company, test_contact: Contact, test_user: User) -> Lead:
    """Create a test lead."""
    lead = Lead(
        id=uuid.uuid4(),
        company_id=test_company.id,
        contact_id=test_contact.id,
        title="Test Lead",
        description="A test lead for testing",
        source="website",
        status=LeadStatusEnum.NEW,
        estimated_value=10000.00,
        currency="USD",
        assigned_to=test_user.id
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


@pytest_asyncio.fixture
async def test_deal(db_session: AsyncSession, test_company: Company, test_contact: Contact, test_user: User) -> Deal:
    """Create a test deal."""
    deal = Deal(
        id=uuid.uuid4(),
        company_id=test_company.id,
        contact_id=test_contact.id,
        title="Test Deal",
        description="A test deal for testing",
        amount=25000.00,
        currency="USD",
        probability=50,
        stage=DealStageEnum.PROSPECTING,
        assigned_to=test_user.id,
        expected_close_date=datetime.now().date() + timedelta(days=30)
    )
    db_session.add(deal)
    await db_session.flush()
    return deal


@pytest_asyncio.fixture
async def test_task(db_session: AsyncSession, test_company: Company, test_user: User) -> Task:
    """Create a test task."""
    task = Task(
        id=uuid.uuid4(),
        company_id=test_company.id,
        title="Test Task",
        description="A test task for testing",
        status=TaskStatusEnum.PENDING,
        priority=TaskPriorityEnum.MEDIUM,
        due_date=datetime.now() + timedelta(days=7),
        assigned_to=test_user.id,
        created_by=test_user.id
    )
    db_session.add(task)
    await db_session.flush()
    return task


@pytest.fixture
def owner_token(test_owner: Owner) -> str:
    """Generate owner JWT token."""
    credentials = JWTManager.generate_credentials(
        sub=test_owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"]
    )
    return credentials["access"]


@pytest.fixture
def user_token(test_user: User) -> str:
    """Generate user JWT token."""
    credentials = JWTManager.generate_credentials(
        sub=test_user.id,
        company_id=test_user.company_id,
        role=test_user.role.value,
        permissions=test_user.permissions or []
    )
    return credentials["access"]


@pytest.fixture
def operator_token(test_operator: User) -> str:
    """Generate operator JWT token."""
    credentials = JWTManager.generate_credentials(
        sub=test_operator.id,
        company_id=test_operator.company_id,
        role=test_operator.role.value,
        permissions=test_operator.permissions or []
    )
    return credentials["access"]


@pytest.fixture
def auth_headers(user_token: str) -> dict:
    """Get auth headers for requests."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def owner_auth_headers(owner_token: str) -> dict:
    """Get owner auth headers for requests."""
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def operator_auth_headers(operator_token: str) -> dict:
    """Get operator auth headers for requests."""
    return {"Authorization": f"Bearer {operator_token}"}
