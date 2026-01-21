import pytest
from httpx import AsyncClient

from utils.managers import JWTManager, TokenType


class TestRegister:
    """Tests for the /api/v1/auth/register endpoint."""

    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"
        assert data["email"] == "john.doe@example.com"
        assert data["is_active"] is False
        assert "credentials" in data
        assert "access" in data["credentials"]
        assert "refresh" in data["credentials"]

    async def test_register_duplicate_email(self, client: AsyncClient, test_user):
        """Test registration with existing email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Another",
                "last_name": "User",
                "email": test_user.email,
                "password": "securepassword123",
            },
        )
        assert response.status_code == 409
        assert "User already exists" in response.json()["detail"]

    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "invalid-email",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        """Test registration with short password fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "password": "short",
            },
        )
        assert response.status_code == 422

    async def test_register_missing_fields(self, client: AsyncClient):
        """Test registration with missing fields fails."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "John",
            },
        )
        assert response.status_code == 422


class TestLogin:
    """Tests for the /api/v1/auth/login endpoint."""

    async def test_login_success(self, client: AsyncClient, test_user):
        """Test successful login."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert "credentials" in data
        assert "access" in data["credentials"]
        assert "refresh" in data["credentials"]

    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpassword123",
            },
        )
        assert response.status_code == 403
        assert "Email or password incorrect" in response.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent user fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "somepassword123",
            },
        )
        assert response.status_code == 401
        assert "User not found" in response.json()["detail"]

    async def test_login_invalid_email_format(self, client: AsyncClient):
        """Test login with invalid email format fails."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "invalid-email",
                "password": "somepassword123",
            },
        )
        assert response.status_code == 422


class TestRefreshToken:
    """Tests for the /api/v1/auth/refresh endpoint."""

    async def test_refresh_token_success(self, client: AsyncClient, test_user):
        """Test successful token refresh."""
        credentials = JWTManager.generate_credentials(test_user.id)

        response = await client.get(
            "/api/v1/auth/refresh",
            params={"token": credentials["refresh"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access" in data

    async def test_refresh_with_access_token_fails(self, client: AsyncClient, test_user):
        """Test refresh with access token instead of refresh token fails."""
        credentials = JWTManager.generate_credentials(test_user.id)

        response = await client.get(
            "/api/v1/auth/refresh",
            params={"token": credentials["access"]},
        )
        assert response.status_code == 401

    async def test_refresh_with_invalid_token(self, client: AsyncClient):
        """Test refresh with invalid token fails."""
        response = await client.get(
            "/api/v1/auth/refresh",
            params={"token": "invalid-token"},
        )
        assert response.status_code == 401

    async def test_refresh_without_token(self, client: AsyncClient):
        """Test refresh without token fails."""
        response = await client.get("/api/v1/auth/refresh")
        assert response.status_code == 422
