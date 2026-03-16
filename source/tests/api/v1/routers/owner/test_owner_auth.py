"""
Tests for owner authentication endpoints
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.owner import Owner
from db.models.enums import RoleEnum
from utils.managers import PasswordManager, JWTManager


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
    async def test_login_owner_sets_cookies(self, client: AsyncClient, test_owner):
        """Test that login sets httpOnly auth cookies."""
        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": test_owner.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 200
        cookies = response.cookies
        assert "access_token" in cookies or any(
            "access_token" in h for h in response.headers.get_list("set-cookie")
        )

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
        assert "Invalid email or password" in response.json()["detail"]

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
        assert "Invalid email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_owner_invalid_email_format(self, client: AsyncClient):
        """Test login with invalid email format returns 422."""
        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": "not-an-email",
                "password": "testpassword123"
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_owner_inactive(self, client: AsyncClient, db_session: AsyncSession):
        """Test login with inactive owner account returns 403."""
        inactive_owner = Owner(
            id=uuid.uuid4(),
            email=f"inactive_{uuid.uuid4().hex[:8]}@test.com",
            password_hash=PasswordManager.hash("testpassword123"),
            first_name="Inactive",
            last_name="Owner",
            phone="+1111111111",
            is_active=False,
            email_verified=True,
        )
        db_session.add(inactive_owner)
        await db_session.flush()

        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": inactive_owner.email,
                "password": "testpassword123"
            }
        )
        assert response.status_code == 403
        assert "inactive" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_owner_unverified_returns_temporary_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test login with unverified email returns temporary token for password set."""
        unverified_owner = Owner(
            id=uuid.uuid4(),
            email=f"unverified_{uuid.uuid4().hex[:8]}@test.com",
            password_hash=PasswordManager.hash("temppass123"),
            first_name="Unverified",
            last_name="Owner",
            phone="+2222222222",
            is_active=True,
            email_verified=False,
        )
        db_session.add(unverified_owner)
        await db_session.flush()

        response = await client.post(
            "/api/v1/owner/auth/login",
            json={
                "email": unverified_owner.email,
                "password": "temppass123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "temporary_token" in data
        # Should not have full credentials
        assert "credentials" not in data or data.get("credentials") is None


class TestOwnerLogout:
    """Tests for POST /api/v1/owner/auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self, client: AsyncClient):
        """Test that logout clears auth cookies."""
        response = await client.post("/api/v1/owner/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"
        # Check that cookies are cleared via set-cookie headers
        set_cookie_headers = response.headers.get_list("set-cookie")
        cookie_names = [h.split("=")[0] for h in set_cookie_headers]
        assert "access_token" in cookie_names
        assert "refresh_token" in cookie_names

    @pytest.mark.asyncio
    async def test_logout_after_login(self, client: AsyncClient, test_owner):
        """Test full login then logout flow."""
        # Login first
        login_resp = await client.post(
            "/api/v1/owner/auth/login",
            json={"email": test_owner.email, "password": "testpassword123"}
        )
        assert login_resp.status_code == 200

        # Logout
        logout_resp = await client.post("/api/v1/owner/auth/logout")
        assert logout_resp.status_code == 200


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
        assert data["last_name"] == test_owner.last_name
        assert "id" in data
        assert "is_active" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_get_current_owner_unauthorized(self, client: AsyncClient):
        """Test getting owner profile without auth fails."""
        response = await client.get("/api/v1/owner/auth/me")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_current_owner_with_user_token(self, client: AsyncClient, user_token):
        """Test that a regular user token cannot access owner /me endpoint."""
        response = await client.get(
            "/api/v1/owner/auth/me",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        # Owner.current() should reject non-owner tokens
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_current_owner_with_invalid_token(self, client: AsyncClient):
        """Test /me with garbage token returns 401/403."""
        response = await client.get(
            "/api/v1/owner/auth/me",
            headers={"Authorization": "Bearer invalid-garbage-token"}
        )
        assert response.status_code in [401, 403]
