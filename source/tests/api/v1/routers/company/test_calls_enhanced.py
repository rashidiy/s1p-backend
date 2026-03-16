"""
Tests for enhanced call management endpoints (outcomes, linking, history)
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestSetCallOutcome:
    """Tests for PUT /api/v1/company/calls/{call_id}/outcome"""

    @pytest.mark.asyncio
    async def test_set_outcome_success(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Set a valid call outcome."""
        response = await client.put(
            f"/api/v1/company/calls/{test_call_event.id}/outcome",
            headers=auth_headers,
            json={
                "outcome": "interested",
                "disposition_notes": "Client wants a demo"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_set_outcome_invalid_value(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Invalid outcome value returns 400."""
        response = await client.put(
            f"/api/v1/company/calls/{test_call_event.id}/outcome",
            headers=auth_headers,
            json={"outcome": "invalid_outcome_value"}
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_set_outcome_not_found(self, client: AsyncClient, auth_headers):
        """Setting outcome on non-existent call returns 404."""
        response = await client.put(
            "/api/v1/company/calls/9999999/outcome",
            headers=auth_headers,
            json={"outcome": "interested"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_set_outcome_without_notes(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Outcome can be set without disposition notes."""
        response = await client.put(
            f"/api/v1/company/calls/{test_call_event.id}/outcome",
            headers=auth_headers,
            json={"outcome": "no_answer"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_set_outcome_unauthorized(self, client: AsyncClient, test_call_event):
        """Unauthenticated request fails."""
        response = await client.put(
            f"/api/v1/company/calls/{test_call_event.id}/outcome",
            json={"outcome": "interested"}
        )
        assert response.status_code in [401, 403, 422]


class TestLinkCallToCRM:
    """Tests for POST /api/v1/company/calls/{call_id}/link"""

    @pytest.mark.asyncio
    async def test_link_call_to_contact(
        self, client: AsyncClient, auth_headers, test_call_event, test_contact
    ):
        """Link call to a contact."""
        response = await client.post(
            f"/api/v1/company/calls/{test_call_event.id}/link",
            headers=auth_headers,
            json={"contact_id": str(test_contact.id)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["links"]["contact_id"] == str(test_contact.id)

    @pytest.mark.asyncio
    async def test_link_call_to_lead(
        self, client: AsyncClient, auth_headers, test_call_event, test_lead
    ):
        """Link call to a lead."""
        response = await client.post(
            f"/api/v1/company/calls/{test_call_event.id}/link",
            headers=auth_headers,
            json={"lead_id": str(test_lead.id)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["links"]["lead_id"] == str(test_lead.id)

    @pytest.mark.asyncio
    async def test_link_call_to_deal(
        self, client: AsyncClient, auth_headers, test_call_event, test_deal
    ):
        """Link call to a deal."""
        response = await client.post(
            f"/api/v1/company/calls/{test_call_event.id}/link",
            headers=auth_headers,
            json={"deal_id": str(test_deal.id)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["links"]["deal_id"] == str(test_deal.id)

    @pytest.mark.asyncio
    async def test_link_call_to_nonexistent_contact(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Linking to non-existent contact returns 404."""
        response = await client.post(
            f"/api/v1/company/calls/{test_call_event.id}/link",
            headers=auth_headers,
            json={"contact_id": str(uuid4())}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_nonexistent_call(self, client: AsyncClient, auth_headers):
        """Linking non-existent call returns 404."""
        response = await client.post(
            "/api/v1/company/calls/9999999/link",
            headers=auth_headers,
            json={"contact_id": str(uuid4())}
        )
        assert response.status_code == 404


class TestCallHistory:
    """Tests for GET /api/v1/company/calls/history"""

    @pytest.mark.asyncio
    async def test_get_call_history(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Get call history returns paginated results."""
        response = await client.get(
            "/api/v1/company/calls/history",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_call_history_pagination(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Call history supports pagination."""
        response = await client.get(
            "/api/v1/company/calls/history",
            headers=auth_headers,
            params={"page": 1, "page_size": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    @pytest.mark.asyncio
    async def test_call_history_search_by_phone(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Call history search by phone number."""
        response = await client.get(
            "/api/v1/company/calls/history",
            headers=auth_headers,
            params={"search": test_call_event.phone_1}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestCallOutcomesSummary:
    """Tests for GET /api/v1/company/calls/outcomes/summary"""

    @pytest.mark.asyncio
    async def test_get_outcomes_summary(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Get call outcomes summary."""
        response = await client.get(
            "/api/v1/company/calls/outcomes/summary",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_calls" in data
        assert "by_outcome" in data
        assert data["total_calls"] >= 1

    @pytest.mark.asyncio
    async def test_outcomes_summary_empty(self, client: AsyncClient, auth_headers):
        """Summary with no calls returns zero totals."""
        response = await client.get(
            "/api/v1/company/calls/outcomes/summary",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 0


class TestAutoLinkSuggestions:
    """Tests for GET /api/v1/company/calls/auto-link-suggestions/{phone}"""

    @pytest.mark.asyncio
    async def test_auto_link_suggestions_found(
        self, client: AsyncClient, auth_headers, test_contact
    ):
        """Get auto-link suggestions for a known phone number."""
        response = await client.get(
            f"/api/v1/company/calls/auto-link-suggestions/{test_contact.phone}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "contacts" in data
        assert "leads" in data
        assert "deals" in data
        assert data["phone_number"] == test_contact.phone
        assert len(data["contacts"]) >= 1

    @pytest.mark.asyncio
    async def test_auto_link_suggestions_not_found(
        self, client: AsyncClient, auth_headers
    ):
        """Get suggestions for unknown phone returns empty lists."""
        response = await client.get(
            "/api/v1/company/calls/auto-link-suggestions/+9999999999",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["contacts"] == []
        assert data["leads"] == []
        assert data["deals"] == []


class TestCallsEnhancedMultiTenancy:
    """Multi-tenancy isolation for enhanced calls endpoints"""

    @pytest.mark.asyncio
    async def test_cannot_set_outcome_other_company_call(
        self, client: AsyncClient, active_auth_headers, test_call_event
    ):
        """Company B cannot set outcome on Company A's call."""
        response = await client.put(
            f"/api/v1/company/calls/{test_call_event.id}/outcome",
            headers=active_auth_headers,
            json={"outcome": "interested"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_link_other_company_call(
        self, client: AsyncClient, active_auth_headers, test_call_event
    ):
        """Company B cannot link Company A's call."""
        response = await client.post(
            f"/api/v1/company/calls/{test_call_event.id}/link",
            headers=active_auth_headers,
            json={"contact_id": str(uuid4())}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_call_history_isolated(
        self, client: AsyncClient, active_auth_headers, test_call_event
    ):
        """Company B's call history does not include Company A's calls."""
        response = await client.get(
            "/api/v1/company/calls/history",
            headers=active_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        call_ids = [c["id"] for c in data["items"]]
        assert test_call_event.id not in call_ids
