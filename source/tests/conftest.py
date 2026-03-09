"""
Test configuration and fixtures for S1P
"""

import asyncio
import os
import sys
import random
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
from db.models.sipuni import Sipuni
from db.models.permission_group import PermissionGroup
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
        provider_config={"cabinet_id": "12345", "security_key": "test-secret"},
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


@pytest.fixture
def company_origin_headers(test_company: Company) -> dict:
    """Get Origin header for company subdomain (required for auth endpoints)."""
    return {"Origin": f"https://{test_company.subdomain}.s1p.com"}


@pytest.fixture
def auth_headers_with_origin(auth_headers: dict, company_origin_headers: dict) -> dict:
    """Auth headers combined with Origin header."""
    return {**auth_headers, **company_origin_headers}


@pytest_asyncio.fixture
async def test_note(db_session: AsyncSession, test_company: Company, test_contact: Contact, test_user: User) -> Note:
    """Create a test note."""
    note = Note(
        id=uuid.uuid4(),
        company_id=test_company.id,
        content="Test note content",
        entity_type="contact",
        entity_id=str(test_contact.id),
        created_by=test_user.id,
    )
    db_session.add(note)
    await db_session.flush()
    return note


@pytest_asyncio.fixture
async def test_call_event(db_session: AsyncSession, test_company: Company, test_user: User) -> CallEvent:
    """Create a test call event."""
    call = CallEvent(
        id=random.randint(1_000_000, 9_999_999),
        company_id=test_company.id,
        provider_type=test_company.provider_type,
        provider_call_id=f"call_{uuid.uuid4().hex[:8]}",
        phone_1="+1234567890",
        phone_2="+0987654321",
        operator_id=test_user.id,
        attempts=1,
    )
    db_session.add(call)
    await db_session.flush()
    return call


@pytest_asyncio.fixture
async def test_sipuni(db_session: AsyncSession, test_user: User) -> Sipuni:
    """Create a test Sipuni integration."""
    cabinet_id = "12345"
    token = f"{cabinet_id}:" + uuid.uuid4().hex[:58]  # 64 chars total
    sipuni = Sipuni(
        id=uuid.uuid4(),
        company_name="Test Sipuni Company",
        cabinet_id=cabinet_id,
        security_key="test-security-key",
        user_id=test_user.id,
        token=token,
        partner_name="Test Partner",
        partner_contact="partner@test.com",
        comment="Test comment",
    )
    db_session.add(sipuni)
    await db_session.flush()
    return sipuni


@pytest_asyncio.fixture
async def test_permission_group(db_session: AsyncSession, test_company: Company) -> PermissionGroup:
    """Create a test custom permission group."""
    group = PermissionGroup(
        id=uuid.uuid4(),
        company_id=test_company.id,
        name=f"test_group_{uuid.uuid4().hex[:8]}",
        description="Test permission group",
        permissions=["leads.read", "contacts.read", "calls.read"],
        is_system=False,
    )
    db_session.add(group)
    await db_session.flush()
    return group


@pytest_asyncio.fixture
async def active_user(db_session: AsyncSession) -> User:
    """Create a second active user in a different company (for isolation tests)."""
    owner2 = Owner(
        id=uuid.uuid4(),
        email=f"owner2_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Other",
        last_name="Owner",
        phone="+9876543210",
        is_active=True,
        email_verified=True
    )
    db_session.add(owner2)
    await db_session.flush()

    company2 = Company(
        id=uuid.uuid4(),
        owner_id=owner2.id,
        name="Other Company",
        subdomain=f"other_{uuid.uuid4().hex[:8]}",
        provider_type=ProviderEnum.SIPUNI,
        provider_config={"cabinet_id": "99999", "security_key": "other-secret"},
        webhook_token=str(uuid.uuid4()),
        is_active=True
    )
    db_session.add(company2)
    await db_session.flush()

    user2 = User(
        id=uuid.uuid4(),
        company_id=company2.id,
        email=f"user2_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Other",
        last_name="User",
        role=RoleEnum.COMPANY_ADMIN,
        permissions=["*"],
        is_active=True,
        email_verified=True
    )
    db_session.add(user2)
    await db_session.flush()
    return user2


@pytest.fixture
def active_auth_headers(active_user: User) -> dict:
    """Auth headers for a different user (not in test_company)."""
    credentials = JWTManager.generate_credentials(
        sub=active_user.id,
        company_id=active_user.company_id,
        role=active_user.role.value,
        permissions=active_user.permissions or []
    )
    return {"Authorization": f"Bearer {credentials['access']}"}


@pytest.fixture
def test_session(db_session: AsyncSession) -> AsyncSession:
    """Alias for db_session (used by some sipuni tests)."""
    return db_session
