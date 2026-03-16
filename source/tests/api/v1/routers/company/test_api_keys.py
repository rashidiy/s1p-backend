"""
Tests for API key management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestCreateApiKey:
    """Tests for POST /api/v1/company/api-keys"""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, client: AsyncClient, auth_headers):
        """Admin can create an API key."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "My Integration Key"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Integration Key"
        assert data["key"].startswith("s1p_")
        assert "id" in data
        assert "key_prefix" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_api_key_returns_full_key_once(self, client: AsyncClient, auth_headers):
        """The full key is returned only on creation."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "One-Time Key"}
        )
        assert response.status_code == 201
        data = response.json()
        full_key = data["key"]
        assert len(full_key) > 8
        assert full_key.startswith("s1p_")

        # List should NOT return the full key
        list_response = await client.get(
            "/api/v1/company/api-keys",
            headers=auth_headers
        )
        assert list_response.status_code == 200
        for item in list_response.json()["items"]:
            assert "key" not in item or item.get("key") is None

    @pytest.mark.asyncio
    async def test_create_api_key_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot create API keys (requires settings.manage)."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=operator_auth_headers,
            json={"name": "Operator Key"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_api_key_empty_name_fails(self, client: AsyncClient, auth_headers):
        """API key with empty name should fail validation."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": ""}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_api_key_unauthorized(self, client: AsyncClient):
        """Unauthenticated request should fail."""
        response = await client.post(
            "/api/v1/company/api-keys",
            json={"name": "No Auth Key"}
        )
        assert response.status_code in [401, 403]


class TestListApiKeys:
    """Tests for GET /api/v1/company/api-keys"""

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, client: AsyncClient, auth_headers):
        """Listing keys when none exist returns empty list."""
        response = await client.get(
            "/api/v1/company/api-keys",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_api_keys_after_create(self, client: AsyncClient, auth_headers):
        """Listed keys should include created key."""
        await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Listed Key"}
        )
        response = await client.get(
            "/api/v1/company/api-keys",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        names = [k["name"] for k in data["items"]]
        assert "Listed Key" in names

    @pytest.mark.asyncio
    async def test_list_api_keys_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot list API keys (requires settings.read)."""
        response = await client.get(
            "/api/v1/company/api-keys",
            headers=operator_auth_headers
        )
        assert response.status_code == 403


class TestRevokeApiKey:
    """Tests for DELETE /api/v1/company/api-keys/{api_key_id}"""

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self, client: AsyncClient, auth_headers):
        """Admin can revoke an API key."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "To Revoke"}
        )
        key_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/company/api-keys/{key_id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self, client: AsyncClient, auth_headers):
        """Revoking non-existent key returns 404."""
        response = await client.delete(
            f"/api/v1/company/api-keys/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_api_key_operator_forbidden(
        self, client: AsyncClient, auth_headers, operator_auth_headers
    ):
        """Operator cannot revoke API keys."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Op Revoke Test"}
        )
        key_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/company/api-keys/{key_id}",
            headers=operator_auth_headers
        )
        assert response.status_code == 403


class TestApiKeyMultiTenancy:
    """Multi-tenancy isolation tests for API keys"""

    @pytest.mark.asyncio
    async def test_cannot_see_other_company_keys(
        self, client: AsyncClient, auth_headers, active_auth_headers
    ):
        """Company B cannot see Company A's API keys."""
        # Create key in company A
        await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Company A Key"}
        )

        # List from company B should not show it
        response = await client.get(
            "/api/v1/company/api-keys",
            headers=active_auth_headers
        )
        assert response.status_code == 200
        names = [k["name"] for k in response.json()["items"]]
        assert "Company A Key" not in names

    @pytest.mark.asyncio
    async def test_cannot_revoke_other_company_key(
        self, client: AsyncClient, auth_headers, active_auth_headers
    ):
        """Company B cannot revoke Company A's API key."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Cross-tenant Key"}
        )
        key_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/company/api-keys/{key_id}",
            headers=active_auth_headers
        )
        assert response.status_code == 404
