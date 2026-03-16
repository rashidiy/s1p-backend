"""
Tests for owner company management endpoints
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from db.models.owner import Owner
from db.models.company import Company
from db.models.enums import ProviderEnum, RoleEnum
from utils.managers import PasswordManager, JWTManager


@pytest_asyncio.fixture
async def second_owner(db_session: AsyncSession) -> Owner:
    """Create a second owner for multi-tenancy tests."""
    owner = Owner(
        id=uuid.uuid4(),
        email=f"owner_b_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Second",
        last_name="Owner",
        phone="+5555555555",
        is_active=True,
        email_verified=True,
    )
    db_session.add(owner)
    await db_session.flush()
    return owner


@pytest.fixture
def second_owner_auth_headers(second_owner: Owner) -> dict:
    """Auth headers for second owner."""
    credentials = JWTManager.generate_credentials(
        sub=second_owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"],
    )
    return {"Authorization": f"Bearer {credentials['access']}"}


@pytest_asyncio.fixture
async def second_owner_company(db_session: AsyncSession, second_owner: Owner) -> Company:
    """Create a company owned by the second owner."""
    company = Company(
        id=uuid.uuid4(),
        owner_id=second_owner.id,
        name="Second Owner Company",
        subdomain=f"second_{uuid.uuid4().hex[:8]}",
        provider_type=ProviderEnum.SIPUNI,
        provider_config={"cabinet_id": "99999", "security_key": "other-secret"},
        webhook_token=str(uuid.uuid4()),
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


class TestCreateCompany:
    """Tests for POST /api/v1/owner/companies/"""

    @pytest.mark.asyncio
    async def test_create_company_success(self, client: AsyncClient, owner_auth_headers):
        """Test successful company creation."""
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "New Test Company",
                "provider_type": "sipuni",
                "provider_config": {
                    "cabinet_id": "12345",
                    "security_key": "test-secret"
                }
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Test Company"
        assert data["provider_type"] == "sipuni"
        assert data["is_active"] is True
        assert "webhook_token" in data

    @pytest.mark.asyncio
    async def test_create_company_with_custom_subdomain(self, client: AsyncClient, owner_auth_headers):
        """Test creating company with explicit subdomain."""
        subdomain = f"custom_{uuid4().hex[:8]}"
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "Custom Subdomain Co",
                "subdomain": subdomain,
                "provider_type": "sipuni",
                "provider_config": {
                    "cabinet_id": "12345",
                    "security_key": "test-secret"
                }
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["subdomain"] == subdomain

    @pytest.mark.asyncio
    async def test_create_company_duplicate_subdomain_rejected(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test that creating a company with an existing subdomain is rejected."""
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "Duplicate Subdomain Co",
                "subdomain": test_company.subdomain,
                "provider_type": "sipuni",
                "provider_config": {
                    "cabinet_id": "12345",
                    "security_key": "test-secret"
                }
            }
        )
        assert response.status_code == 400
        assert "subdomain" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_company_binotel(self, client: AsyncClient, owner_auth_headers):
        """Test creating company with Binotel provider."""
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "Binotel Company",
                "provider_type": "binotel",
                "provider_config": {
                    "cabinet_id": "key123",
                    "security_key": "secret123"
                }
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["provider_type"] == "binotel"

    @pytest.mark.asyncio
    async def test_create_company_invalid_provider(self, client: AsyncClient, owner_auth_headers):
        """Test creating company with invalid provider fails."""
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "Test Company",
                "provider_type": "invalid_provider",
                "provider_config": {
                    "cabinet_id": "12345",
                    "security_key": "secret"
                }
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_company_unauthorized(self, client: AsyncClient):
        """Test creating company without auth fails."""
        response = await client.post(
            "/api/v1/owner/companies",
            json={
                "name": "Test Company",
                "provider_type": "sipuni",
                "provider_config": {}
            }
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_create_company_missing_provider_config_fields(
        self, client: AsyncClient, owner_auth_headers
    ):
        """Test that missing required provider config fields returns 422."""
        response = await client.post(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            json={
                "name": "Bad Config Co",
                "provider_type": "sipuni",
                "provider_config": {"cabinet_id": "123"}  # missing security_key
            }
        )
        assert response.status_code == 422


class TestListCompanies:
    """Tests for GET /api/v1/owner/companies/"""

    @pytest.mark.asyncio
    async def test_list_companies(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test listing owner's companies."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(c["name"] == test_company.name for c in data)

    @pytest.mark.asyncio
    async def test_list_companies_with_search(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test listing companies with search filter by name."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            params={"search": test_company.name}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert all(test_company.name.lower() in c["name"].lower() for c in data)

    @pytest.mark.asyncio
    async def test_list_companies_search_by_subdomain(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test listing companies with search filter by subdomain."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            params={"search": test_company.subdomain}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_companies_search_no_results(
        self, client: AsyncClient, owner_auth_headers
    ):
        """Test listing companies with search that matches nothing."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            params={"search": "zzz_nonexistent_company_xyz"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_companies_pagination(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test listing companies with pagination params."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            params={"page": 1, "page_size": 1}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 1

    @pytest.mark.asyncio
    async def test_list_companies_pagination_page_2_empty(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test that requesting a high page number returns empty list."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers,
            params={"page": 999, "page_size": 50}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_companies_unauthorized(self, client: AsyncClient):
        """Test listing companies without auth fails."""
        response = await client.get("/api/v1/owner/companies")
        assert response.status_code in [401, 403]


class TestGetCompany:
    """Tests for GET /api/v1/owner/companies/{company_id}"""

    @pytest.mark.asyncio
    async def test_get_company(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test getting company details."""
        response = await client.get(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_company.id)
        assert data["name"] == test_company.name
        assert "provider_config" in data
        assert "webhook_token" in data

    @pytest.mark.asyncio
    async def test_get_company_not_found(self, client: AsyncClient, owner_auth_headers):
        """Test getting non-existent company fails."""
        response = await client.get(
            f"/api/v1/owner/companies/{uuid4()}",
            headers=owner_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_company_has_users_count(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test that company detail includes users_count field."""
        response = await client.get(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "users_count" in data
        assert isinstance(data["users_count"], int)


class TestUpdateCompany:
    """Tests for PUT /api/v1/owner/companies/{company_id}"""

    @pytest.mark.asyncio
    async def test_update_company_name(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test updating company name."""
        response = await client.put(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers,
            json={"name": "Updated Company Name"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Company Name"

    @pytest.mark.asyncio
    async def test_update_company_settings(
        self, client: AsyncClient, owner_auth_headers, test_company
    ):
        """Test updating company settings."""
        new_settings = {"timezone": "Asia/Tashkent", "language": "ru"}
        response = await client.put(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers,
            json={"settings": new_settings}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_company_deactivate(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test deactivating company via update."""
        response = await client.put(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers,
            json={"is_active": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_company_not_found(self, client: AsyncClient, owner_auth_headers):
        """Test updating non-existent company returns 404."""
        response = await client.put(
            f"/api/v1/owner/companies/{uuid4()}",
            headers=owner_auth_headers,
            json={"name": "Ghost Company"}
        )
        assert response.status_code == 404


class TestDeleteCompany:
    """Tests for DELETE /api/v1/owner/companies/{company_id}"""

    @pytest.mark.asyncio
    async def test_soft_delete_company(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test soft deleting company."""
        response = await client.delete(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=owner_auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_company_not_found(self, client: AsyncClient, owner_auth_headers):
        """Test deleting non-existent company fails."""
        response = await client.delete(
            f"/api/v1/owner/companies/{uuid4()}",
            headers=owner_auth_headers
        )
        assert response.status_code == 404


class TestActivateDeactivateCompany:
    """Tests for POST /api/v1/owner/companies/{company_id}/activate|deactivate"""

    @pytest.mark.asyncio
    async def test_deactivate_company(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test deactivating company."""
        response = await client.post(
            f"/api/v1/owner/companies/{test_company.id}/deactivate",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_company(self, client: AsyncClient, owner_auth_headers, test_company):
        """Test activating company."""
        # First deactivate
        await client.post(
            f"/api/v1/owner/companies/{test_company.id}/deactivate",
            headers=owner_auth_headers
        )

        # Then activate
        response = await client.post(
            f"/api/v1/owner/companies/{test_company.id}/activate",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_activate_nonexistent_company(self, client: AsyncClient, owner_auth_headers):
        """Test activating a non-existent company returns 404."""
        response = await client.post(
            f"/api/v1/owner/companies/{uuid4()}/activate",
            headers=owner_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_company(self, client: AsyncClient, owner_auth_headers):
        """Test deactivating a non-existent company returns 404."""
        response = await client.post(
            f"/api/v1/owner/companies/{uuid4()}/deactivate",
            headers=owner_auth_headers
        )
        assert response.status_code == 404


class TestMultiTenancyIsolation:
    """Tests that owner A cannot access owner B's companies."""

    @pytest.mark.asyncio
    async def test_owner_cannot_list_other_owners_companies(
        self,
        client: AsyncClient,
        second_owner_auth_headers,
        test_company,
    ):
        """Owner B's list should not include Owner A's companies."""
        response = await client.get(
            "/api/v1/owner/companies",
            headers=second_owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        company_ids = [c["id"] for c in data]
        assert str(test_company.id) not in company_ids

    @pytest.mark.asyncio
    async def test_owner_cannot_get_other_owners_company(
        self,
        client: AsyncClient,
        second_owner_auth_headers,
        test_company,
    ):
        """Owner B cannot GET detail of Owner A's company."""
        response = await client.get(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=second_owner_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_cannot_update_other_owners_company(
        self,
        client: AsyncClient,
        second_owner_auth_headers,
        test_company,
    ):
        """Owner B cannot update Owner A's company."""
        response = await client.put(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=second_owner_auth_headers,
            json={"name": "Hijacked Company"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_cannot_delete_other_owners_company(
        self,
        client: AsyncClient,
        second_owner_auth_headers,
        test_company,
    ):
        """Owner B cannot delete Owner A's company."""
        response = await client.delete(
            f"/api/v1/owner/companies/{test_company.id}",
            headers=second_owner_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_cannot_deactivate_other_owners_company(
        self,
        client: AsyncClient,
        second_owner_auth_headers,
        test_company,
    ):
        """Owner B cannot deactivate Owner A's company."""
        response = await client.post(
            f"/api/v1/owner/companies/{test_company.id}/deactivate",
            headers=second_owner_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_each_owner_sees_only_their_companies(
        self,
        client: AsyncClient,
        owner_auth_headers,
        second_owner_auth_headers,
        test_company,
        second_owner_company,
    ):
        """Each owner sees only their own companies in list."""
        # Owner A
        resp_a = await client.get(
            "/api/v1/owner/companies",
            headers=owner_auth_headers
        )
        assert resp_a.status_code == 200
        ids_a = {c["id"] for c in resp_a.json()}

        # Owner B
        resp_b = await client.get(
            "/api/v1/owner/companies",
            headers=second_owner_auth_headers
        )
        assert resp_b.status_code == 200
        ids_b = {c["id"] for c in resp_b.json()}

        # No overlap
        assert ids_a & ids_b == set()
        assert str(test_company.id) in ids_a
        assert str(second_owner_company.id) in ids_b
