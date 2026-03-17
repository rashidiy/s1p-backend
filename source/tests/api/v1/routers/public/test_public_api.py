"""
Tests for Public REST API + API key authentication
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


# ===== API Key Management Tests =====

class TestCreateApiKey:
    """Tests for POST /api/v1/company/api-keys"""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, client: AsyncClient, auth_headers):
        """Test successful API key creation."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "My Integration"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Integration"
        assert "key" in data
        assert data["key"].startswith("s1p_")
        assert "key_prefix" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_api_key_unauthorized(self, client: AsyncClient):
        """Test creating API key without auth fails."""
        response = await client.post(
            "/api/v1/company/api-keys",
            json={"name": "Test"}
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_create_api_key_missing_name(self, client: AsyncClient, auth_headers):
        """Test creating API key without name fails."""
        response = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 422


class TestListApiKeys:
    """Tests for GET /api/v1/company/api-keys"""

    @pytest.mark.asyncio
    async def test_list_api_keys(self, client: AsyncClient, auth_headers):
        """Test listing API keys."""
        # Create a key first
        await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "List Test Key"}
        )

        response = await client.get(
            "/api/v1/company/api-keys",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1


class TestRevokeApiKey:
    """Tests for DELETE /api/v1/company/api-keys/{id}"""

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client: AsyncClient, auth_headers):
        """Test revoking an API key."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Revoke Test"}
        )
        key_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/company/api-keys/{key_id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self, client: AsyncClient, auth_headers):
        """Test revoking non-existent key fails."""
        response = await client.delete(
            f"/api/v1/company/api-keys/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


# ===== Public API Endpoint Tests =====

class TestPublicApiAuth:
    """Tests for public API authentication via X-API-Key"""

    @pytest.mark.asyncio
    async def test_no_api_key(self, client: AsyncClient):
        """Test accessing public API without key fails."""
        response = await client.get("/api/public/v1/contacts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_api_key(self, client: AsyncClient):
        """Test accessing public API with invalid key fails."""
        response = await client.get(
            "/api/public/v1/contacts",
            headers={"X-API-Key": "invalid_key_12345"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_revoked_api_key(self, client: AsyncClient, auth_headers):
        """Test accessing public API with revoked key fails."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Revoked Key"}
        )
        key_data = create_resp.json()

        await client.delete(
            f"/api/v1/company/api-keys/{key_data['id']}",
            headers=auth_headers
        )

        response = await client.get(
            "/api/public/v1/contacts",
            headers={"X-API-Key": key_data["key"]}
        )
        assert response.status_code == 401


class TestPublicContacts:
    """Tests for GET /api/public/v1/contacts"""

    @pytest.mark.asyncio
    async def test_list_contacts(self, client: AsyncClient, auth_headers, test_contact):
        """Test listing contacts via public API."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Contacts Test"}
        )
        api_key = create_resp.json()["key"]

        response = await client.get(
            "/api/public/v1/contacts",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "has_more" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    @pytest.mark.asyncio
    async def test_contacts_pagination(self, client: AsyncClient, auth_headers, test_contact):
        """Test cursor-based pagination."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Pagination Test"}
        )
        api_key = create_resp.json()["key"]

        response = await client.get(
            "/api/public/v1/contacts",
            headers={"X-API-Key": api_key},
            params={"limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "has_more" in data
        assert isinstance(data["data"], list)


class TestPublicLeads:
    """Tests for GET /api/public/v1/leads"""

    @pytest.mark.asyncio
    async def test_list_leads(self, client: AsyncClient, auth_headers, test_lead):
        """Test listing leads via public API."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Leads Test"}
        )
        api_key = create_resp.json()["key"]

        response = await client.get(
            "/api/public/v1/leads",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "has_more" in data
        assert len(data["data"]) >= 1


class TestPublicDeals:
    """Tests for GET /api/public/v1/deals"""

    @pytest.mark.asyncio
    async def test_list_deals(self, client: AsyncClient, auth_headers, test_deal):
        """Test listing deals via public API."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Deals Test"}
        )
        api_key = create_resp.json()["key"]

        response = await client.get(
            "/api/public/v1/deals",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "has_more" in data
        assert len(data["data"]) >= 1


class TestPublicCalls:
    """Tests for GET /api/public/v1/calls"""

    @pytest.mark.asyncio
    async def test_list_calls(self, client: AsyncClient, auth_headers, test_call_event):
        """Test listing calls via public API."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Calls Test"}
        )
        api_key = create_resp.json()["key"]

        response = await client.get(
            "/api/public/v1/calls",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "has_more" in data


class TestPublicApiResponseFormat:
    """Tests for public API response format consistency"""

    @pytest.mark.asyncio
    async def test_all_endpoints_return_paginated_format(self, client: AsyncClient, auth_headers):
        """Test that all public endpoints return the correct cursor-paginated format."""
        create_resp = await client.post(
            "/api/v1/company/api-keys",
            headers=auth_headers,
            json={"name": "Format Test"}
        )
        api_key = create_resp.json()["key"]

        for endpoint in ["/api/public/v1/contacts", "/api/public/v1/leads",
                         "/api/public/v1/deals", "/api/public/v1/calls"]:
            response = await client.get(
                endpoint,
                headers={"X-API-Key": api_key}
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data, f"Missing 'data' in {endpoint}"
            assert "has_more" in data, f"Missing 'has_more' in {endpoint}"
            assert isinstance(data["data"], list), f"'data' not a list in {endpoint}"
