"""
Tests for permission group management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestListPermissionGroups:
    """Tests for GET /api/v1/company/permission-groups"""

    @pytest.mark.asyncio
    async def test_list_permission_groups(self, client: AsyncClient, auth_headers, test_permission_group):
        """Test listing permission groups."""
        response = await client.get(
            "/api/v1/company/permission-groups",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "groups" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_permission_groups_unauthorized(self, client: AsyncClient):
        """Test listing permission groups without auth fails."""
        response = await client.get("/api/v1/company/permission-groups")
        assert response.status_code in [401, 403, 422]


class TestGetPermissionGroup:
    """Tests for GET /api/v1/company/permission-groups/{group_id}"""

    @pytest.mark.asyncio
    async def test_get_permission_group(self, client: AsyncClient, auth_headers, test_permission_group):
        """Test getting permission group details."""
        response = await client.get(
            f"/api/v1/company/permission-groups/{test_permission_group.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_permission_group.id)
        assert data["name"] == test_permission_group.name
        assert isinstance(data["permissions"], list)

    @pytest.mark.asyncio
    async def test_get_permission_group_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent permission group fails."""
        response = await client.get(
            f"/api/v1/company/permission-groups/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestCreatePermissionGroup:
    """Tests for POST /api/v1/company/permission-groups"""

    @pytest.mark.asyncio
    async def test_create_permission_group_success(self, client: AsyncClient, auth_headers):
        """Test successful permission group creation."""
        response = await client.post(
            "/api/v1/company/permission-groups",
            headers=auth_headers,
            json={
                "name": f"Sales Team {uuid4().hex[:6]}",
                "description": "Permissions for sales team",
                "permissions": ["leads.read", "leads.write", "contacts.read", "deals.read"]
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert "Sales Team" in data["name"]
        assert data["is_system"] is False
        assert len(data["permissions"]) == 4

    @pytest.mark.asyncio
    async def test_create_permission_group_duplicate_name(
        self, client: AsyncClient, auth_headers, test_permission_group
    ):
        """Test creating permission group with duplicate name fails."""
        response = await client.post(
            "/api/v1/company/permission-groups",
            headers=auth_headers,
            json={
                "name": test_permission_group.name,
                "permissions": ["leads.read"]
            }
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_permission_group_missing_permissions(self, client: AsyncClient, auth_headers):
        """Test creating permission group without permissions fails."""
        response = await client.post(
            "/api/v1/company/permission-groups",
            headers=auth_headers,
            json={
                "name": "Empty Group"
            }
        )
        assert response.status_code == 422


class TestUpdatePermissionGroup:
    """Tests for PUT /api/v1/company/permission-groups/{group_id}"""

    @pytest.mark.asyncio
    async def test_update_permission_group(self, client: AsyncClient, auth_headers, test_permission_group):
        """Test updating a custom permission group."""
        response = await client.put(
            f"/api/v1/company/permission-groups/{test_permission_group.id}",
            headers=auth_headers,
            json={
                "name": f"Updated Group {uuid4().hex[:6]}",
                "permissions": ["leads.read", "leads.write"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "Updated Group" in data["name"]
        assert len(data["permissions"]) == 2

    @pytest.mark.asyncio
    async def test_update_permission_group_not_found(self, client: AsyncClient, auth_headers):
        """Test updating non-existent permission group fails."""
        response = await client.put(
            f"/api/v1/company/permission-groups/{uuid4()}",
            headers=auth_headers,
            json={"name": "Test"}
        )
        assert response.status_code == 404


class TestDeletePermissionGroup:
    """Tests for DELETE /api/v1/company/permission-groups/{group_id}"""

    @pytest.mark.asyncio
    async def test_delete_permission_group(self, client: AsyncClient, auth_headers, test_permission_group):
        """Test soft deleting a custom permission group."""
        response = await client.delete(
            f"/api/v1/company/permission-groups/{test_permission_group.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_permission_group_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent permission group fails."""
        response = await client.delete(
            f"/api/v1/company/permission-groups/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404
