"""
Tests for tasks management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime, timedelta


class TestCreateTask:
    """Tests for POST /api/v1/company/tasks/"""

    @pytest.mark.asyncio
    async def test_create_task_success(self, client: AsyncClient, auth_headers, test_user):
        """Test successful task creation."""
        due_date = (datetime.now() + timedelta(days=7)).isoformat()
        response = await client.post(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            json={
                "title": "New Task",
                "description": "Task description",
                "due_date": due_date,
                "assigned_to": str(test_user.id)
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Task"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_task_minimal(self, client: AsyncClient, auth_headers):
        """Test creating task with minimal fields."""
        response = await client.post(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            json={
                "title": "Minimal Task"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Task"
        # status and priority have defaults
        assert "status" in data
        assert "priority" in data

    @pytest.mark.asyncio
    async def test_create_task_linked_to_contact(self, client: AsyncClient, auth_headers, test_contact):
        """Test creating task linked to contact."""
        response = await client.post(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            json={
                "title": "Contact Task",
                "entity_type": "contact",
                "entity_id": str(test_contact.id)
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "contact"
        assert data["entity_id"] == str(test_contact.id)

    @pytest.mark.asyncio
    async def test_create_task_linked_to_lead(self, client: AsyncClient, auth_headers, test_lead):
        """Test creating task linked to lead."""
        response = await client.post(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            json={
                "title": "Lead Task",
                "entity_type": "lead",
                "entity_id": str(test_lead.id)
            }
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_task_unauthorized(self, client: AsyncClient):
        """Test creating task without auth fails."""
        response = await client.post(
            "/api/v1/company/tasks/",
            json={"title": "Test"}
        )
        assert response.status_code in [401, 403, 422]


class TestListTasks:
    """Tests for GET /api/v1/company/tasks/"""

    @pytest.mark.asyncio
    async def test_list_tasks(self, client: AsyncClient, auth_headers, test_task):
        """Test listing tasks."""
        response = await client.get(
            "/api/v1/company/tasks/",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_tasks_filter_status(self, client: AsyncClient, auth_headers, test_task):
        """Test filtering tasks by status."""
        response = await client.get(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            params={"status_filter": "pending"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_filter_priority(self, client: AsyncClient, auth_headers, test_task):
        """Test filtering tasks by priority."""
        response = await client.get(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            params={"priority": "medium"}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_my_tasks(self, client: AsyncClient, auth_headers, test_task):
        """Test listing my assigned tasks."""
        response = await client.get(
            "/api/v1/company/tasks/",
            headers=auth_headers,
            params={"my_tasks": True}
        )
        assert response.status_code == 200


class TestGetTask:
    """Tests for GET /api/v1/company/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_get_task(self, client: AsyncClient, auth_headers, test_task):
        """Test getting task details."""
        response = await client.get(
            f"/api/v1/company/tasks/{test_task.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_task.id)
        assert data["title"] == test_task.title

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent task fails."""
        response = await client.get(
            f"/api/v1/company/tasks/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestGetMyTasksToday:
    """Tests for GET /api/v1/company/tasks/my-today"""

    @pytest.mark.asyncio
    async def test_get_my_tasks_today(self, client: AsyncClient, auth_headers):
        """Test getting my tasks for today."""
        response = await client.get(
            "/api/v1/company/tasks/my-today",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestUpdateTask:
    """Tests for PUT /api/v1/company/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_update_task(self, client: AsyncClient, auth_headers, test_task):
        """Test updating task."""
        response = await client.put(
            f"/api/v1/company/tasks/{test_task.id}",
            headers=auth_headers,
            json={
                "title": "Updated Task",
                "description": "Updated description"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Task"

    @pytest.mark.asyncio
    async def test_update_task_status(self, client: AsyncClient, auth_headers, test_task):
        """Test updating task due date."""
        new_due_date = (datetime.now() + timedelta(days=14)).isoformat()
        response = await client.put(
            f"/api/v1/company/tasks/{test_task.id}",
            headers=auth_headers,
            json={
                "due_date": new_due_date
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "due_date" in data


class TestDeleteTask:
    """Tests for DELETE /api/v1/company/tasks/{task_id}"""

    @pytest.mark.asyncio
    async def test_delete_task_soft(self, client: AsyncClient, auth_headers, test_task):
        """Test soft deleting task."""
        response = await client.delete(
            f"/api/v1/company/tasks/{test_task.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent task fails."""
        response = await client.delete(
            f"/api/v1/company/tasks/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestCompleteTask:
    """Tests for POST /api/v1/company/tasks/{task_id}/complete"""

    @pytest.mark.asyncio
    async def test_complete_task(self, client: AsyncClient, auth_headers, test_task):
        """Test completing task."""
        response = await client.post(
            f"/api/v1/company/tasks/{test_task.id}/complete",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
