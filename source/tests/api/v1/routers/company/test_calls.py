"""
Tests for call management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestListCalls:
    """Tests for GET /api/v1/company/calls"""

    @pytest.mark.asyncio
    async def test_list_calls(self, client: AsyncClient, auth_headers, test_call_event):
        """Test listing calls."""
        response = await client.get(
            "/api/v1/company/calls",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_calls_with_pagination(self, client: AsyncClient, auth_headers):
        """Test listing calls with skip/limit."""
        response = await client.get(
            "/api/v1/company/calls",
            headers=auth_headers,
            params={"skip": 0, "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_calls_unauthorized(self, client: AsyncClient):
        """Test listing calls without auth fails."""
        response = await client.get("/api/v1/company/calls")
        assert response.status_code in [401, 403, 422]


class TestGetCall:
    """Tests for GET /api/v1/company/calls/{call_id}"""

    @pytest.mark.asyncio
    async def test_get_call(self, client: AsyncClient, auth_headers, test_call_event):
        """Test getting call details."""
        response = await client.get(
            f"/api/v1/company/calls/{test_call_event.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_call_event.id)

    @pytest.mark.asyncio
    async def test_get_call_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent call fails."""
        response = await client.get(
            f"/api/v1/company/calls/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestGetCallRecording:
    """Tests for GET /api/v1/company/calls/{call_id}/recording"""

    @pytest.mark.asyncio
    async def test_get_recording_no_recording(self, client: AsyncClient, auth_headers, test_call_event):
        """Test getting recording when none exists returns 404."""
        response = await client.get(
            f"/api/v1/company/calls/{test_call_event.id}/recording",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_recording_not_found(self, client: AsyncClient, auth_headers):
        """Test getting recording for non-existent call fails."""
        response = await client.get(
            f"/api/v1/company/calls/{uuid4()}/recording",
            headers=auth_headers
        )
        assert response.status_code == 404
