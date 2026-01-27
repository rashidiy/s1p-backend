"""
Tests for user authentication endpoints
"""

import pytest
import uuid
from httpx import AsyncClient

from utils.managers import JWTManager, TokenType


class TestUserRegister:
    """Tests for POST /api/v1/auth/register"""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, test_company):
        """Test successful user registration."""
        unique_email = f"newuser_{uuid.uuid4().hex[:8]}@test.com"
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "New",
                "last_name": "User",
                "email": unique_email,
                "password": "securepassword123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == unique_email
        assert data["first_name"] == "New"
        assert "credentials" in data
        assert "access" in data["credentials"]
        assert "refresh" in data["credentials"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user):
        """Test registration with existing email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Another",
                "last_name": "User",
                "email": test_user.email,
                "password": "securepassword123"
            }
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": "invalid-email",
                "password": "securepassword123"
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        """Test registration with short password fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": "test@test.com",
                "password": "short"
            }
        )
        assert response.status_code == 422


class TestUserLogin:
    """Tests for POST /api/v1/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user):
        """Test successful user login."""
        response = await client.post(
            "/api/v1/auth/login",
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
    async def test_login_wrong_email(self, client: AsyncClient):
        """Test login with non-existent email fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpassword123"
            }
        )
        assert response.status_code == 403


class TestTokenRefresh:
    """Tests for POST /api/v1/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user):
        """Test successful token refresh."""
        # First login to get tokens
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "testpassword123"
            }
        )
        assert login_response.status_code == 200
        refresh_token = login_response.json()["credentials"]["refresh"]

        # Refresh the token (now POST with body)
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
