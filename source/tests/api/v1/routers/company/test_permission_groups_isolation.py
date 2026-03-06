"""
Tests for permission group tenant isolation

Verifies that:
- Company A cannot see Company B's custom groups
- All companies can see system groups
- System groups cannot be modified or deleted
- Company A cannot modify or delete Company B's groups
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from db.models.company import Company
from db.models.enums import RoleEnum, ProviderEnum
from db.models.owner import Owner
from db.models.permission_group import PermissionGroup
from db.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from utils.managers import PasswordManager, JWTManager


# --- Fixtures for a second company (Company B) ---


@pytest_asyncio.fixture
async def company_b_owner(db_session: AsyncSession) -> Owner:
    """Create a second owner for Company B."""
    owner = Owner(
        id=uuid.uuid4(),
        email=f"owner_b_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Owner",
        last_name="B",
        phone="+9876543210",
        is_active=True,
        email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()
    return owner


@pytest_asyncio.fixture
async def company_b(db_session: AsyncSession, company_b_owner: Owner) -> Company:
    """Create a second company (Company B)."""
    company = Company(
        id=uuid.uuid4(),
        owner_id=company_b_owner.id,
        name="Company B",
        subdomain=f"compb_{uuid.uuid4().hex[:8]}",
        provider_type=ProviderEnum.SIPUNI,
        provider_config={"cabinet_id": "99999", "security_key": "secret-b"},
        webhook_token=str(uuid.uuid4()),
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def company_b_user(db_session: AsyncSession, company_b: Company) -> User:
    """Create an admin user for Company B."""
    user = User(
        id=uuid.uuid4(),
        company_id=company_b.id,
        email=f"user_b_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="User",
        last_name="B",
        phone="+9876543211",
        role=RoleEnum.COMPANY_ADMIN,
        permissions=["*"],
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def company_b_token(company_b_user: User) -> str:
    """Generate JWT token for Company B user."""
    credentials = JWTManager.generate_credentials(
        sub=company_b_user.id,
        company_id=company_b_user.company_id,
        role=company_b_user.role.value,
        permissions=company_b_user.permissions or [],
    )
    return credentials["access"]


@pytest.fixture
def company_b_headers(company_b_token: str) -> dict:
    """Auth headers for Company B user."""
    return {"Authorization": f"Bearer {company_b_token}"}


# --- Fixtures for permission groups ---


@pytest_asyncio.fixture
async def company_a_group(db_session: AsyncSession, test_company: Company) -> PermissionGroup:
    """Create a custom permission group owned by Company A (test_company)."""
    group = PermissionGroup(
        id=uuid.uuid4(),
        company_id=test_company.id,
        name=f"company_a_group_{uuid.uuid4().hex[:8]}",
        description="Company A custom group",
        permissions=["leads.read", "contacts.read"],
        is_system=False,
    )
    db_session.add(group)
    await db_session.flush()
    return group


@pytest_asyncio.fixture
async def company_b_group(db_session: AsyncSession, company_b: Company) -> PermissionGroup:
    """Create a custom permission group owned by Company B."""
    group = PermissionGroup(
        id=uuid.uuid4(),
        company_id=company_b.id,
        name=f"company_b_group_{uuid.uuid4().hex[:8]}",
        description="Company B custom group",
        permissions=["deals.read", "tasks.read"],
        is_system=False,
    )
    db_session.add(group)
    await db_session.flush()
    return group


@pytest_asyncio.fixture
async def system_group(db_session: AsyncSession) -> PermissionGroup:
    """Create a system permission group (shared across all companies)."""
    group = PermissionGroup(
        id=uuid.uuid4(),
        company_id=None,
        name=f"system_group_{uuid.uuid4().hex[:8]}",
        description="System-wide shared group",
        permissions=["leads.read", "contacts.read", "calls.read"],
        is_system=True,
    )
    db_session.add(group)
    await db_session.flush()
    return group


# --- Test classes ---


class TestCrossCompanyIsolation:
    """Company A cannot see, modify, or delete Company B's groups."""

    @pytest.mark.asyncio
    async def test_company_a_cannot_see_company_b_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        company_a_group: PermissionGroup,
        company_b_group: PermissionGroup,
    ):
        """List as Company A user -- should see own group but not Company B's group."""
        response = await client.get(
            "/api/v1/company/permission-groups",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["groups"]]

        # Company A's group must be visible
        assert str(company_a_group.id) in group_ids

        # Company B's group must NOT be visible
        assert str(company_b_group.id) not in group_ids

    @pytest.mark.asyncio
    async def test_company_b_cannot_see_company_a_groups(
        self,
        client: AsyncClient,
        company_b_headers: dict,
        company_a_group: PermissionGroup,
        company_b_group: PermissionGroup,
    ):
        """List as Company B user -- should see own group but not Company A's group."""
        response = await client.get(
            "/api/v1/company/permission-groups",
            headers=company_b_headers,
        )
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["groups"]]

        assert str(company_b_group.id) in group_ids
        assert str(company_a_group.id) not in group_ids

    @pytest.mark.asyncio
    async def test_company_a_cannot_get_company_b_group_by_id(
        self,
        client: AsyncClient,
        auth_headers: dict,
        company_b_group: PermissionGroup,
    ):
        """GET by ID for another company's group should return 404."""
        response = await client.get(
            f"/api/v1/company/permission-groups/{company_b_group.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_modify_other_company_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        company_b_group: PermissionGroup,
    ):
        """PUT on another company's group should fail with 404."""
        response = await client.put(
            f"/api/v1/company/permission-groups/{company_b_group.id}",
            headers=auth_headers,
            json={"name": "Hijacked Group"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_company_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        company_b_group: PermissionGroup,
    ):
        """DELETE on another company's group should fail with 404."""
        response = await client.delete(
            f"/api/v1/company/permission-groups/{company_b_group.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestSystemGroupVisibility:
    """System groups are visible to all companies but immutable."""

    @pytest.mark.asyncio
    async def test_company_can_see_system_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        system_group: PermissionGroup,
    ):
        """Any company should see system groups in the list."""
        response = await client.get(
            "/api/v1/company/permission-groups",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["groups"]]
        assert str(system_group.id) in group_ids

    @pytest.mark.asyncio
    async def test_company_b_can_see_system_groups(
        self,
        client: AsyncClient,
        company_b_headers: dict,
        system_group: PermissionGroup,
    ):
        """Company B should also see system groups in the list."""
        response = await client.get(
            "/api/v1/company/permission-groups",
            headers=company_b_headers,
        )
        assert response.status_code == 200
        data = response.json()
        group_ids = [g["id"] for g in data["groups"]]
        assert str(system_group.id) in group_ids

    @pytest.mark.asyncio
    async def test_can_get_system_group_by_id(
        self,
        client: AsyncClient,
        auth_headers: dict,
        system_group: PermissionGroup,
    ):
        """GET by ID for a system group should succeed."""
        response = await client.get(
            f"/api/v1/company/permission-groups/{system_group.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_system"] is True
        assert data["id"] == str(system_group.id)


class TestSystemGroupImmutability:
    """System groups cannot be modified or deleted."""

    @pytest.mark.asyncio
    async def test_cannot_modify_system_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        system_group: PermissionGroup,
    ):
        """PUT on a system group should return 403."""
        response = await client.put(
            f"/api/v1/company/permission-groups/{system_group.id}",
            headers=auth_headers,
            json={"name": "Hacked System Group"},
        )
        assert response.status_code == 403
        assert "System groups cannot be modified" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_cannot_delete_system_groups(
        self,
        client: AsyncClient,
        auth_headers: dict,
        system_group: PermissionGroup,
    ):
        """DELETE on a system group should return 403."""
        response = await client.delete(
            f"/api/v1/company/permission-groups/{system_group.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert "System groups cannot be deleted" in response.json()["detail"]
