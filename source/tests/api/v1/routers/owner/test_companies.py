"""
Tests for owner company management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


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
        assert response.status_code in [401, 403, 422]


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
    async def test_list_companies_unauthorized(self, client: AsyncClient):
        """Test listing companies without auth fails."""
        response = await client.get("/api/v1/owner/companies")
        assert response.status_code in [401, 403, 422]


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
