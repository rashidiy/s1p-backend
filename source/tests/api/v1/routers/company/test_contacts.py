"""
Tests for contacts management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestCreateContact:
    """Tests for POST /api/v1/company/contacts/"""

    @pytest.mark.asyncio
    async def test_create_contact_success(self, client: AsyncClient, auth_headers):
        """Test successful contact creation."""
        response = await client.post(
            "/api/v1/company/contacts",
            headers=auth_headers,
            json={
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
                "phone": "+1987654321",
                "company_name": "Tech Corp",
                "position": "CTO"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"
        assert data["email"] == "jane.smith@example.com"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_contact_minimal(self, client: AsyncClient, auth_headers):
        """Test creating contact with minimal fields."""
        response = await client.post(
            "/api/v1/company/contacts",
            headers=auth_headers,
            json={
                "first_name": "Minimal"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Minimal"

    @pytest.mark.asyncio
    async def test_create_contact_duplicate_email(self, client: AsyncClient, auth_headers, test_contact):
        """Test creating contact with duplicate email fails."""
        response = await client.post(
            "/api/v1/company/contacts",
            headers=auth_headers,
            json={
                "first_name": "Another",
                "email": test_contact.email
            }
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_contact_unauthorized(self, client: AsyncClient):
        """Test creating contact without auth fails."""
        response = await client.post(
            "/api/v1/company/contacts",
            json={"first_name": "Test"}
        )
        assert response.status_code in [401, 403, 422]


class TestListContacts:
    """Tests for GET /api/v1/company/contacts/"""

    @pytest.mark.asyncio
    async def test_list_contacts(self, client: AsyncClient, auth_headers, test_contact):
        """Test listing contacts."""
        response = await client.get(
            "/api/v1/company/contacts",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_contacts_pagination(self, client: AsyncClient, auth_headers):
        """Test contacts pagination."""
        response = await client.get(
            "/api/v1/company/contacts",
            headers=auth_headers,
            params={"page": 1, "page_size": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    @pytest.mark.asyncio
    async def test_list_contacts_search(self, client: AsyncClient, auth_headers, test_contact):
        """Test contacts search."""
        response = await client.get(
            "/api/v1/company/contacts",
            headers=auth_headers,
            params={"search": test_contact.first_name}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestGetContact:
    """Tests for GET /api/v1/company/contacts/{contact_id}"""

    @pytest.mark.asyncio
    async def test_get_contact(self, client: AsyncClient, auth_headers, test_contact):
        """Test getting contact details."""
        response = await client.get(
            f"/api/v1/company/contacts/{test_contact.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_contact.id)
        assert data["first_name"] == test_contact.first_name

    @pytest.mark.asyncio
    async def test_get_contact_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent contact fails."""
        response = await client.get(
            f"/api/v1/company/contacts/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateContact:
    """Tests for PUT /api/v1/company/contacts/{contact_id}"""

    @pytest.mark.asyncio
    async def test_update_contact(self, client: AsyncClient, auth_headers, test_contact):
        """Test updating contact."""
        response = await client.put(
            f"/api/v1/company/contacts/{test_contact.id}",
            headers=auth_headers,
            json={
                "first_name": "Updated",
                "position": "New Position"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["position"] == "New Position"

    @pytest.mark.asyncio
    async def test_update_contact_not_found(self, client: AsyncClient, auth_headers):
        """Test updating non-existent contact fails."""
        response = await client.put(
            f"/api/v1/company/contacts/{uuid4()}",
            headers=auth_headers,
            json={"first_name": "Test"}
        )
        assert response.status_code == 404


class TestDeleteContact:
    """Tests for DELETE /api/v1/company/contacts/{contact_id}"""

    @pytest.mark.asyncio
    async def test_delete_contact_soft(self, client: AsyncClient, auth_headers, test_contact):
        """Test soft deleting contact."""
        response = await client.delete(
            f"/api/v1/company/contacts/{test_contact.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_contact_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent contact fails."""
        response = await client.delete(
            f"/api/v1/company/contacts/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestContactActivity:
    """Tests for GET /api/v1/company/contacts/{contact_id}/activity"""

    @pytest.mark.asyncio
    async def test_get_contact_activity(self, client: AsyncClient, auth_headers, test_contact):
        """Test getting contact activity."""
        response = await client.get(
            f"/api/v1/company/contacts/{test_contact.id}/activity",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "contact_id" in data
        assert "leads" in data
        assert "deals" in data
        assert "calls" in data
