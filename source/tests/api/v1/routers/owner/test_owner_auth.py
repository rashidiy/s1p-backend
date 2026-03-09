"""
Tests for owner authentication endpoints
"""

import pytest
from httpx import AsyncClient


class TestOwnerLogin:
    """Tests for POST /api/v1/owner/auth/login"""

    @pytest.mark.asyncio
    async def test_login_owner_success(self, client: AsyncClient, test_owner):
        """Test successful owner login."""
        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": test_owner.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_owner.email
        assert "credentials" in data
        assert "access" in data["credentials"]
        assert "refresh" in data["credentials"]

    @pytest.mark.asyncio
    async def test_login_owner_wrong_password(self, client: AsyncClient, test_owner):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": test_owner.email,
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_owner_not_found(self, client: AsyncClient):
        """Test login with non-existent email fails."""
        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 401


class TestOwnerProfile:
    """Tests for GET /api/v1/owner/auth/me"""

    @pytest.mark.asyncio
    async def test_get_current_owner(self, client: AsyncClient, owner_auth_headers, test_owner):
        """Test getting current owner profile."""
        response = await client.get(
            "/api/v1/owner/auth/me",
            headers=owner_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_owner.email
        assert data["first_name"] == test_owner.first_name

    @pytest.mark.asyncio
    async def test_get_current_owner_unauthorized(self, client: AsyncClient):
        """Test getting owner profile without auth fails."""
        response = await client.get("/api/v1/owner/auth/me")
        assert response.status_code in [401, 403, 422]
