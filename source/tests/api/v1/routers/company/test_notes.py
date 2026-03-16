"""
Tests for notes management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestCreateNote:
    """Tests for POST /api/v1/company/notes"""

    @pytest.mark.asyncio
    async def test_create_note_success(self, client: AsyncClient, auth_headers, test_contact):
        """Test successful note creation."""
        response = await client.post(
            "/api/v1/company/notes",
            headers=auth_headers,
            json={
                "content": "This is a test note",
                "entity_type": "contact",
                "entity_id": str(test_contact.id)
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "This is a test note"
        assert data["entity_type"] == "contact"
        assert data["entity_id"] == str(test_contact.id)

    @pytest.mark.asyncio
    async def test_create_note_for_lead(self, client: AsyncClient, auth_headers, test_lead):
        """Test creating a note linked to a lead."""
        response = await client.post(
            "/api/v1/company/notes",
            headers=auth_headers,
            json={
                "content": "Lead follow-up note",
                "entity_type": "lead",
                "entity_id": str(test_lead.id)
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "lead"

    @pytest.mark.asyncio
    async def test_create_note_empty_content(self, client: AsyncClient, auth_headers, test_contact):
        """Test creating note with empty content fails."""
        response = await client.post(
            "/api/v1/company/notes",
            headers=auth_headers,
            json={
                "content": "",
                "entity_type": "contact",
                "entity_id": str(test_contact.id)
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_unauthorized(self, client: AsyncClient, test_contact):
        """Test creating note without auth fails."""
        response = await client.post(
            "/api/v1/company/notes",
            json={
                "content": "Test",
                "entity_type": "contact",
                "entity_id": str(test_contact.id)
            }
        )
        assert response.status_code in [401, 403]


class TestListNotes:
    """Tests for GET /api/v1/company/notes"""

    @pytest.mark.asyncio
    async def test_list_notes(self, client: AsyncClient, auth_headers, test_note):
        """Test listing notes."""
        response = await client.get(
            "/api/v1/company/notes",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_contact(self, client: AsyncClient, auth_headers, test_note, test_contact):
        """Test filtering notes by contact_id."""
        response = await client.get(
            "/api/v1/company/notes",
            headers=auth_headers,
            params={"contact_id": str(test_contact.id)}
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_notes_search(self, client: AsyncClient, auth_headers, test_note):
        """Test searching notes by content."""
        response = await client.get(
            "/api/v1/company/notes",
            headers=auth_headers,
            params={"search": "test note"}
        )
        assert response.status_code == 200


class TestGetNote:
    """Tests for GET /api/v1/company/notes/{note_id}"""

    @pytest.mark.asyncio
    async def test_get_note(self, client: AsyncClient, auth_headers, test_note):
        """Test getting note details."""
        response = await client.get(
            f"/api/v1/company/notes/{test_note.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_note.id)
        assert data["content"] == test_note.content

    @pytest.mark.asyncio
    async def test_get_note_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent note fails."""
        response = await client.get(
            f"/api/v1/company/notes/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateNote:
    """Tests for PUT /api/v1/company/notes/{note_id}"""

    @pytest.mark.asyncio
    async def test_update_note(self, client: AsyncClient, auth_headers, test_note):
        """Test updating note content."""
        response = await client.put(
            f"/api/v1/company/notes/{test_note.id}",
            headers=auth_headers,
            json={"content": "Updated note content"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated note content"

    @pytest.mark.asyncio
    async def test_update_note_not_found(self, client: AsyncClient, auth_headers):
        """Test updating non-existent note fails."""
        response = await client.put(
            f"/api/v1/company/notes/{uuid4()}",
            headers=auth_headers,
            json={"content": "Test"}
        )
        assert response.status_code == 404


class TestDeleteNote:
    """Tests for DELETE /api/v1/company/notes/{note_id}"""

    @pytest.mark.asyncio
    async def test_delete_note(self, client: AsyncClient, auth_headers, test_note):
        """Test soft deleting note."""
        response = await client.delete(
            f"/api/v1/company/notes/{test_note.id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self, client: AsyncClient, auth_headers):
        """Test deleting non-existent note fails."""
        response = await client.delete(
            f"/api/v1/company/notes/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestEntityNotes:
    """Tests for GET /api/v1/company/notes/timeline/{entity_type}/{entity_id}"""

    @pytest.mark.asyncio
    async def test_get_entity_notes(self, client: AsyncClient, auth_headers, test_note, test_contact):
        """Test getting all notes for an entity."""
        response = await client.get(
            f"/api/v1/company/notes/timeline/contact/{test_contact.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "contact"
        assert data["entity_id"] == str(test_contact.id)
        assert "notes" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_entity_notes_invalid_type(self, client: AsyncClient, auth_headers):
        """Test getting notes with invalid entity type fails."""
        response = await client.get(
            f"/api/v1/company/notes/timeline/invalid/{uuid4()}",
            headers=auth_headers
        )
        assert response.status_code == 400
