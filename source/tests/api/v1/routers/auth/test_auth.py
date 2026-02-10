"""
Tests for user authentication endpoints
"""

import pytest
import uuid
from httpx import AsyncClient

from utils.managers import JWTManager, TokenType


class TestUserLogin:
    """Tests for POST /api/v1/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user, test_company):
        """Test successful user login with Origin header."""
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": f"https://{test_company.subdomain}.siptools.com"},
            json={
                "email": test_user.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert "credentials" in data
        assert "access" in data["credentials"]
        assert "refresh" in data["credentials"]

    @pytest.mark.asyncio
    async def test_login_missing_origin(self, client: AsyncClient, test_user):
        """Test login without Origin header fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 400
        assert "origin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_wrong_subdomain(self, client: AsyncClient, test_user):
        """Test login with non-existent company subdomain fails."""
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://nonexistent.siptools.com"},
            json={
                "email": test_user.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_login_wrong_email(self, client: AsyncClient, test_company):
        """Test login with non-existent email fails."""
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": f"https://{test_company.subdomain}.siptools.com"},
            json={
                "email": "nonexistent@test.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user, test_company):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": f"https://{test_company.subdomain}.siptools.com"},
            json={
                "email": test_user.email,
                "password": "wrongpassword123"
            }
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client: AsyncClient, test_company):
        """Test login with invalid email format fails."""
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": f"https://{test_company.subdomain}.siptools.com"},
            json={
                "email": "invalid-email",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 422


class TestTokenRefresh:
    """Tests for POST /api/v1/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user, test_company):
        """Test successful token refresh."""
        # First login to get tokens
        login_response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": f"https://{test_company.subdomain}.siptools.com"},
            json={
                "email": test_user.email,
                "password": "testpassword123"
            }
        )
        assert login_response.status_code == 200
        refresh_token = login_response.json()["credentials"]["refresh"]

        # Refresh the token
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access" in data

        # Verify the new access token is valid
        payload = JWTManager.verify(data["access"], TokenType.ACCESS)
        assert str(payload.sub) == str(test_user.id)

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self, client: AsyncClient):
        """Test refresh with invalid token fails."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"}
        )
        assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_refresh_with_access_token(self, client: AsyncClient, user_token):
        """Test refresh with access token instead of refresh token fails."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": user_token}
        )
        # Access token should not work as refresh token
        assert response.status_code in [401, 403, 422]
