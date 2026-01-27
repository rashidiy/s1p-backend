"""
Tests for deals management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import date, timedelta


class TestCreateDeal:
    """Tests for POST /api/v1/company/deals/"""

    @pytest.mark.asyncio
    async def test_create_deal_success(self, client: AsyncClient, auth_headers, test_contact):
        """Test successful deal creation."""
        response = await client.post(
            "/api/v1/company/deals/",
            headers=auth_headers,
            json={
                "title": "New Deal",
                "contact_id": str(test_contact.id),
                "amount": 25000.00,
                "probability": 50,
                "expected_close_date": str(date.today() + timedelta(days=30))
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Deal"
        assert float(data["amount"]) == 25000.00
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_deal_minimal(self, client: AsyncClient, auth_headers):
        """Test creating deal with minimal fields."""
        response = await client.post(
            "/api/v1/company/deals/",
            headers=auth_headers,
            json={
                "title": "Minimal Deal",
                "amount": 1000.00
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Deal"
        # Stage defaults to PROSPECTING
        assert "stage" in data

    @pytest.mark.asyncio
    async def test_create_deal_with_lead(self, client: AsyncClient, auth_headers, test_lead):
        """Test creating deal from lead."""
        response = await client.post(
            "/api/v1/company/deals/",
            headers=auth_headers,
            json={
                "title": "Deal from Lead",
                "lead_id": str(test_lead.id),
                "amount": 15000.00
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["lead_id"] == str(test_lead.id)

    @pytest.mark.asyncio
    async def test_create_deal_unauthorized(self, client: AsyncClient):
        """Test creating deal without auth fails."""
        response = await client.post(
            "/api/v1/company/deals/",
            json={"title": "Test", "value": 1000}
        )
        assert response.status_code in [401, 403, 422]


class TestListDeals:
    """Tests for GET /api/v1/company/deals/"""

    @pytest.mark.asyncio
    async def test_list_deals(self, client: AsyncClient, auth_headers, test_deal):
        """Test listing deals."""
        response = await client.get(
            "/api/v1/company/deals/",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_deals_filter_stage(self, client: AsyncClient, auth_headers, test_deal):
        """Test filtering deals by stage."""
        response = await client.get(
            "/api/v1/company/deals/",
            headers=auth_headers,
            params={"stage": "prospecting"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_deals_value_range(self, client: AsyncClient, auth_headers, test_deal):
        """Test filtering deals by value range."""
        response = await client.get(
            "/api/v1/company/deals/",
            headers=auth_headers,
            params={"min_value": 1000, "max_value": 100000}
        )
        assert response.status_code == 200


class TestGetDeal:
    """Tests for GET /api/v1/company/deals/{deal_id}"""

    @pytest.mark.asyncio
    async def test_get_deal(self, client: AsyncClient, auth_headers, test_deal):
        """Test getting deal details."""
        response = await client.get(
            f"/api/v1/company/deals/{test_deal.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_deal.id)
        assert data["title"] == test_deal.title

    @pytest.mark.asyncio
    async def test_get_deal_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent deal fails."""
        response = await client.get(
            f"/api/v1/company/deals/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateDeal:
    """Tests for PUT /api/v1/company/deals/{deal_id}"""

    @pytest.mark.asyncio
    async def test_update_deal(self, client: AsyncClient, auth_headers, test_deal):
        """Test updating deal."""
        response = await client.put(
            f"/api/v1/company/deals/{test_deal.id}",
            headers=auth_headers,
            json={
                "title": "Updated Deal",
                "amount": 30000.00
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Deal"
        assert float(data["amount"]) == 30000.00

    @pytest.mark.asyncio
    async def test_update_deal_stage(self, client: AsyncClient, auth_headers, test_deal):
        """Test updating deal stage."""
        response = await client.put(
            f"/api/v1/company/deals/{test_deal.id}",
            headers=auth_headers,
            json={
                "probability": 75
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["probability"] == 75


class TestDeleteDeal:
    """Tests for DELETE /api/v1/company/deals/{deal_id}"""

    @pytest.mark.asyncio
    async def test_delete_deal_soft(self, client: AsyncClient, auth_headers, test_deal):
        """Test soft deleting deal."""
        response = await client.delete(
            f"/api/v1/company/deals/{test_deal.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_deal_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent deal fails."""
        response = await client.delete(
            f"/api/v1/company/deals/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestWinLoseDeal:
    """Tests for POST /api/v1/company/deals/{deal_id}/win|lose"""

    @pytest.mark.asyncio
    async def test_win_deal(self, client: AsyncClient, auth_headers, test_deal):
        """Test marking deal as won."""
        response = await client.post(
            f"/api/v1/company/deals/{test_deal.id}/win",
            headers=auth_headers,
            params={"win_reason": "Client signed contract"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "closed_won"

    @pytest.mark.asyncio
    async def test_lose_deal(self, client: AsyncClient, auth_headers, test_deal):
        """Test marking deal as lost."""
        response = await client.post(
            f"/api/v1/company/deals/{test_deal.id}/lose",
            headers=auth_headers,
            params={"loss_reason": "Budget constraints"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stage"] == "closed_lost"


class TestPipelineSummary:
    """Tests for GET /api/v1/company/deals/pipeline/summary"""

    @pytest.mark.asyncio
    async def test_get_pipeline_summary(self, client: AsyncClient, auth_headers, test_deal):
        """Test getting pipeline summary."""
        response = await client.get(
            "/api/v1/company/deals/pipeline/summary",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should contain stage breakdown
        assert isinstance(data, dict)
