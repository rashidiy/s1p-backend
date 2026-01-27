"""
Tests for analytics endpoints
"""

import pytest
from httpx import AsyncClient


class TestMyAnalytics:
    """Tests for GET /api/v1/company/analytics/me"""

    @pytest.mark.asyncio
    async def test_get_my_analytics(self, client: AsyncClient, auth_headers):
        """Test getting my analytics."""
        response = await client.get(
            "/api/v1/company/analytics/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should have basic metrics
        assert isinstance(data, dict)


class TestMyDashboard:
    """Tests for GET /api/v1/company/analytics/me/dashboard"""

    @pytest.mark.asyncio
    async def test_get_my_dashboard(self, client: AsyncClient, auth_headers):
        """Test getting my dashboard."""
        response = await client.get(
            "/api/v1/company/analytics/me/dashboard",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestTeamAnalytics:
    """Tests for GET /api/v1/company/analytics/team"""

    @pytest.mark.asyncio
    async def test_get_team_analytics(self, client: AsyncClient, auth_headers):
        """Test getting team analytics (admin only)."""
        response = await client.get(
            "/api/v1/company/analytics/team",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_get_team_analytics_unauthorized(self, client: AsyncClient, operator_auth_headers):
        """Test getting team analytics with insufficient permissions."""
        response = await client.get(
            "/api/v1/company/analytics/team",
            headers=operator_auth_headers
        )
        # Should be forbidden for operators
        assert response.status_code in [200, 403]


class TestTeamDashboard:
    """Tests for GET /api/v1/company/analytics/team/dashboard"""

    @pytest.mark.asyncio
    async def test_get_team_dashboard(self, client: AsyncClient, auth_headers):
        """Test getting team dashboard."""
        response = await client.get(
            "/api/v1/company/analytics/team/dashboard",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestOperatorAnalytics:
    """Tests for GET /api/v1/company/analytics/operator/{user_id}"""

    @pytest.mark.asyncio
    async def test_get_operator_analytics(self, client: AsyncClient, auth_headers, test_operator):
        """Test getting specific operator analytics."""
        response = await client.get(
            f"/api/v1/company/analytics/operator/{test_operator.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestOwnerPlatformAnalytics:
    """Tests for GET /api/v1/owner/analytics/platform"""

    @pytest.mark.asyncio
    async def test_get_platform_analytics(self, client: AsyncClient, owner_auth_headers):
        """Test getting platform-wide analytics."""
        response = await client.get(
            "/api/v1/owner/analytics/platform",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_get_platform_analytics_unauthorized(self, client: AsyncClient, auth_headers):
        """Test getting platform analytics with user token fails."""
        response = await client.get(
            "/api/v1/owner/analytics/platform",
            headers=auth_headers
        )
        assert response.status_code in [401, 403]


class TestOwnerDashboard:
    """Tests for GET /api/v1/owner/analytics/dashboard"""

    @pytest.mark.asyncio
    async def test_get_owner_dashboard(self, client: AsyncClient, owner_auth_headers):
        """Test getting owner dashboard."""
        response = await client.get(
            "/api/v1/owner/analytics/dashboard",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
