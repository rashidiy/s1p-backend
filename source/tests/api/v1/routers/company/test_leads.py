"""
Tests for leads management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestCreateLead:
    """Tests for POST /api/v1/company/leads/"""

    @pytest.mark.asyncio
    async def test_create_lead_success(self, client: AsyncClient, auth_headers, test_contact):
        """Test successful lead creation."""
        response = await client.post(
            "/api/v1/company/leads",
            headers=auth_headers,
            json={
                "title": "New Lead",
                "contact_id": str(test_contact.id),
                "source": "website",
                "estimated_value": 5000.00,
                "description": "A potential customer"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Lead"
        assert data["source"] == "website"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_lead_minimal(self, client: AsyncClient, auth_headers):
        """Test creating lead with minimal fields."""
        response = await client.post(
            "/api/v1/company/leads",
            headers=auth_headers,
            json={
                "title": "Minimal Lead"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Lead"
        # Status defaults to NEW enum
        assert "status" in data

    @pytest.mark.asyncio
    async def test_create_lead_with_assignment(self, client: AsyncClient, auth_headers, test_user):
        """Test creating lead with assignment."""
        response = await client.post(
            "/api/v1/company/leads",
            headers=auth_headers,
            json={
                "title": "Assigned Lead",
                "assigned_to": str(test_user.id)
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["assigned_to"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_create_lead_unauthorized(self, client: AsyncClient):
        """Test creating lead without auth fails."""
        response = await client.post(
            "/api/v1/company/leads",
            json={"title": "Test"}
        )
        assert response.status_code in [401, 403, 422]


class TestListLeads:
    """Tests for GET /api/v1/company/leads/"""

    @pytest.mark.asyncio
    async def test_list_leads(self, client: AsyncClient, auth_headers, test_lead):
        """Test listing leads."""
        response = await client.get(
            "/api/v1/company/leads",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_leads_filter_status(self, client: AsyncClient, auth_headers, test_lead):
        """Test filtering leads by status."""
        response = await client.get(
            "/api/v1/company/leads",
            headers=auth_headers,
            params={"status_filter": "new"}
        )
        assert response.status_code == 200
        data = response.json()
        assert all(item["status"] == "new" for item in data["items"])

    @pytest.mark.asyncio
    async def test_list_leads_search(self, client: AsyncClient, auth_headers, test_lead):
        """Test searching leads."""
        response = await client.get(
            "/api/v1/company/leads",
            headers=auth_headers,
            params={"search": test_lead.title}
        )
        assert response.status_code == 200


class TestGetLead:
    """Tests for GET /api/v1/company/leads/{lead_id}"""

    @pytest.mark.asyncio
    async def test_get_lead(self, client: AsyncClient, auth_headers, test_lead):
        """Test getting lead details."""
        response = await client.get(
            f"/api/v1/company/leads/{test_lead.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_lead.id)
        assert data["title"] == test_lead.title

    @pytest.mark.asyncio
    async def test_get_lead_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent lead fails."""
        response = await client.get(
            f"/api/v1/company/leads/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateLead:
    """Tests for PUT /api/v1/company/leads/{lead_id}"""

    @pytest.mark.asyncio
    async def test_update_lead(self, client: AsyncClient, auth_headers, test_lead):
        """Test updating lead."""
        response = await client.put(
            f"/api/v1/company/leads/{test_lead.id}",
            headers=auth_headers,
            json={
                "title": "Updated Lead Title",
                "description": "Updated description"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Lead Title"

    @pytest.mark.asyncio
    async def test_update_lead_value(self, client: AsyncClient, auth_headers, test_lead):
        """Test updating lead estimated value."""
        response = await client.put(
            f"/api/v1/company/leads/{test_lead.id}",
            headers=auth_headers,
            json={
                "estimated_value": 15000.00
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert float(data["estimated_value"]) == 15000.00


class TestDeleteLead:
    """Tests for DELETE /api/v1/company/leads/{lead_id}"""

    @pytest.mark.asyncio
    async def test_delete_lead_soft(self, client: AsyncClient, auth_headers, test_lead):
        """Test soft deleting lead."""
        response = await client.delete(
            f"/api/v1/company/leads/{test_lead.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_lead_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent lead fails."""
        response = await client.delete(
            f"/api/v1/company/leads/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestConvertLead:
    """Tests for POST /api/v1/company/leads/{lead_id}/convert"""

    @pytest.mark.asyncio
    async def test_convert_lead_to_deal(self, client: AsyncClient, auth_headers, test_lead):
        """Test converting lead to deal."""
        response = await client.post(
            f"/api/v1/company/leads/{test_lead.id}/convert",
            headers=auth_headers,
            json={
                "deal_title": "Converted Deal",
                "deal_value": 20000.00
            }
        )
        # Could be 200 or 201 depending on implementation
        assert response.status_code in [200, 201]


class TestAssignLead:
    """Tests for POST /api/v1/company/leads/{lead_id}/assign"""

    @pytest.mark.asyncio
    async def test_assign_lead(self, client: AsyncClient, auth_headers, test_lead, test_user):
        """Test assigning lead to operator."""
        response = await client.post(
            f"/api/v1/company/leads/{test_lead.id}/assign",
            headers=auth_headers,
            params={
                "assigned_to": str(test_user.id)
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["assigned_to"] == str(test_user.id)
