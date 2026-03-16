"""
Tests for user management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestInviteUser:
    """Tests for POST /api/v1/company/users/invite"""

    @pytest.mark.asyncio
    async def test_invite_user_success(self, client: AsyncClient, auth_headers):
        """Test successful user invitation."""
        response = await client.post(
            "/api/v1/company/users/invite",
            headers=auth_headers,
            json={
                "email": "newoperator@test.com",
                "first_name": "New",
                "last_name": "Operator",
                "role": "company_operator"
            }
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["email"] == "newoperator@test.com"

    @pytest.mark.asyncio
    async def test_invite_user_manager(self, client: AsyncClient, auth_headers):
        """Test inviting a manager user."""
        response = await client.post(
            "/api/v1/company/users/invite",
            headers=auth_headers,
            json={
                "email": "newmanager@test.com",
                "first_name": "New",
                "last_name": "Manager",
                "role": "company_manager"
            }
        )
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_invite_user_unauthorized(self, client: AsyncClient):
        """Test inviting user without auth fails."""
        response = await client.post(
            "/api/v1/company/users/invite",
            json={
                "email": "test@test.com",
                "first_name": "Test",
                "role": "company_operator"
            }
        )
        assert response.status_code in [401, 403]


class TestListUsers:
    """Tests for GET /api/v1/company/users/"""

    @pytest.mark.asyncio
    async def test_list_users(self, client: AsyncClient, auth_headers, test_user):
        """Test listing users."""
        response = await client.get(
            "/api/v1/company/users",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_users_filter_role(self, client: AsyncClient, auth_headers):
        """Test filtering users by role."""
        response = await client.get(
            "/api/v1/company/users",
            headers=auth_headers,
            params={"role": "company_admin"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_users_search(self, client: AsyncClient, auth_headers, test_user):
        """Test searching users."""
        response = await client.get(
            "/api/v1/company/users",
            headers=auth_headers,
            params={"search": test_user.first_name}
        )
        assert response.status_code == 200


class TestGetUser:
    """Tests for GET /api/v1/company/users/{user_id}"""

    @pytest.mark.asyncio
    async def test_get_user(self, client: AsyncClient, auth_headers, test_user):
        """Test getting user details."""
        response = await client.get(
            f"/api/v1/company/users/{test_user.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent user fails."""
        response = await client.get(
            f"/api/v1/company/users/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateUser:
    """Tests for PUT /api/v1/company/users/{user_id}"""

    @pytest.mark.asyncio
    async def test_update_user(self, client: AsyncClient, auth_headers, test_operator):
        """Test updating user."""
        response = await client.put(
            f"/api/v1/company/users/{test_operator.id}",
            headers=auth_headers,
            json={
                "first_name": "Updated",
                "phone": "+9998887776"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["phone"] == "+9998887776"

    @pytest.mark.asyncio
    async def test_update_user_role(self, client: AsyncClient, auth_headers, test_operator):
        """Test updating user role."""
        response = await client.put(
            f"/api/v1/company/users/{test_operator.id}",
            headers=auth_headers,
            json={
                "role": "company_manager"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "company_manager"


class TestDeleteUser:
    """Tests for DELETE /api/v1/company/users/{user_id}"""

    @pytest.mark.asyncio
    async def test_delete_user_soft(self, client: AsyncClient, auth_headers, test_operator):
        """Test soft deleting user."""
        response = await client.delete(
            f"/api/v1/company/users/{test_operator.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent user fails."""
        response = await client.delete(
            f"/api/v1/company/users/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestActivateDeactivateUser:
    """Tests for POST /api/v1/company/users/{user_id}/activate|deactivate"""

    @pytest.mark.asyncio
    async def test_deactivate_user(self, client: AsyncClient, auth_headers, test_operator):
        """Test deactivating user."""
        response = await client.post(
            f"/api/v1/company/users/{test_operator.id}/deactivate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_activate_user(self, client: AsyncClient, auth_headers, test_operator):
        """Test activating user."""
        # First deactivate
        await client.post(
            f"/api/v1/company/users/{test_operator.id}/deactivate",
            headers=auth_headers
        )

        # Then activate
        response = await client.post(
            f"/api/v1/company/users/{test_operator.id}/activate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True


class TestChangePassword:
    """Tests for POST /api/v1/auth/reset-password"""

    @pytest.mark.asyncio
    async def test_change_password(self, client: AsyncClient, auth_headers):
        """Test changing own password."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            headers=auth_headers,
            json={
                "old_password": "testpassword123",
                "new_password": "NewPassword123"
            }
        )
        assert response.status_code in [200, 204]

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, client: AsyncClient, auth_headers):
        """Test changing password with wrong current password fails."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            headers=auth_headers,
            json={
                "old_password": "WrongPassword1",
                "new_password": "NewPassword123"
            }
        )
        assert response.status_code in [400, 403]
