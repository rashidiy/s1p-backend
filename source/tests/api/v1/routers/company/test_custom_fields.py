"""
Tests for custom field definitions API
"""

import pytest
from httpx import AsyncClient

from utils.validators.custom_fields import validate_custom_field_values


class TestCustomFieldDefinitionCRUD:
    """Test CRUD operations for custom field definitions."""

    @pytest.mark.asyncio
    async def test_create_text_field(self, client: AsyncClient, auth_headers: dict):
        """Create a text custom field definition."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "contact",
                "field_name": "nickname",
                "field_type": "text",
                "sort_order": 0,
                "is_required": False,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["field_name"] == "nickname"
        assert data["field_type"] == "text"
        assert data["entity_type"] == "contact"
        assert data["is_required"] is False

    @pytest.mark.asyncio
    async def test_create_dropdown_field(self, client: AsyncClient, auth_headers: dict):
        """Create a dropdown custom field with options."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "lead",
                "field_name": "priority_level",
                "field_type": "dropdown",
                "options": ["low", "medium", "high", "critical"],
                "sort_order": 1,
                "is_required": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["field_type"] == "dropdown"
        assert data["options"] == ["low", "medium", "high", "critical"]
        assert data["is_required"] is True

    @pytest.mark.asyncio
    async def test_create_dropdown_without_options_fails(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Dropdown field without options should fail."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "contact",
                "field_name": "category",
                "field_type": "dropdown",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_number_field(self, client: AsyncClient, auth_headers: dict):
        """Create a number custom field."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "deal",
                "field_name": "employee_count",
                "field_type": "number",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["field_type"] == "number"

    @pytest.mark.asyncio
    async def test_create_boolean_field(self, client: AsyncClient, auth_headers: dict):
        """Create a boolean custom field."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "contact",
                "field_name": "is_vip",
                "field_type": "boolean",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["field_type"] == "boolean"

    @pytest.mark.asyncio
    async def test_create_date_field(self, client: AsyncClient, auth_headers: dict):
        """Create a date custom field."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "contact",
                "field_name": "birthday",
                "field_type": "date",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["field_type"] == "date"

    @pytest.mark.asyncio
    async def test_create_duplicate_field_fails(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Cannot create two fields with the same name for the same entity type."""
        payload = {
            "entity_type": "contact",
            "field_name": "unique_field_test",
            "field_type": "text",
        }
        response1 = await client.post(
            "/api/v1/company/custom-fields", json=payload, headers=auth_headers
        )
        assert response1.status_code == 201

        response2 = await client.post(
            "/api/v1/company/custom-fields", json=payload, headers=auth_headers
        )
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_entity_type_fails(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Invalid entity_type should be rejected."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "invalid_entity",
                "field_name": "test",
                "field_type": "text",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_field_type_fails(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Invalid field_type should be rejected."""
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "contact",
                "field_name": "test",
                "field_type": "invalid_type",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_definitions(self, client: AsyncClient, auth_headers: dict):
        """List all custom field definitions."""
        for name in ["list_field_a", "list_field_b"]:
            await client.post(
                "/api/v1/company/custom-fields",
                json={"entity_type": "contact", "field_name": name, "field_type": "text"},
                headers=auth_headers,
            )

        response = await client.get(
            "/api/v1/company/custom-fields?entity_type=contact",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        names = [d["field_name"] for d in data]
        assert "list_field_a" in names
        assert "list_field_b" in names

    @pytest.mark.asyncio
    async def test_get_definition(self, client: AsyncClient, auth_headers: dict):
        """Get a single custom field definition."""
        create_response = await client.post(
            "/api/v1/company/custom-fields",
            json={"entity_type": "lead", "field_name": "get_test_field", "field_type": "text"},
            headers=auth_headers,
        )
        field_id = create_response.json()["id"]

        response = await client.get(
            f"/api/v1/company/custom-fields/{field_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["field_name"] == "get_test_field"

    @pytest.mark.asyncio
    async def test_update_definition(self, client: AsyncClient, auth_headers: dict):
        """Update a custom field definition."""
        create_response = await client.post(
            "/api/v1/company/custom-fields",
            json={"entity_type": "deal", "field_name": "update_test", "field_type": "text"},
            headers=auth_headers,
        )
        field_id = create_response.json()["id"]

        response = await client.put(
            f"/api/v1/company/custom-fields/{field_id}",
            json={"field_name": "updated_name", "is_required": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["field_name"] == "updated_name"
        assert response.json()["is_required"] is True

    @pytest.mark.asyncio
    async def test_delete_definition(self, client: AsyncClient, auth_headers: dict):
        """Soft delete a custom field definition."""
        create_response = await client.post(
            "/api/v1/company/custom-fields",
            json={"entity_type": "task", "field_name": "delete_test", "field_type": "text"},
            headers=auth_headers,
        )
        field_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/v1/company/custom-fields/{field_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Should not appear in list
        list_response = await client.get(
            "/api/v1/company/custom-fields?entity_type=task",
            headers=auth_headers,
        )
        field_ids = [d["id"] for d in list_response.json()]
        assert field_id not in field_ids

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """Unauthenticated requests should fail."""
        response = await client.get("/api/v1/company/custom-fields")
        assert response.status_code in [401, 403]


class TestCustomFieldLimit:
    """Test the 20-field-per-entity-type limit."""

    @pytest.mark.asyncio
    async def test_max_20_fields_per_entity(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Cannot create more than 20 custom fields per entity type."""
        for i in range(20):
            response = await client.post(
                "/api/v1/company/custom-fields",
                json={
                    "entity_type": "note",
                    "field_name": f"limit_field_{i}",
                    "field_type": "text",
                },
                headers=auth_headers,
            )
            assert response.status_code == 201, f"Failed on field {i}: {response.json()}"

        # 21st should fail
        response = await client.post(
            "/api/v1/company/custom-fields",
            json={
                "entity_type": "note",
                "field_name": "limit_field_21",
                "field_type": "text",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestCustomFieldValidator:
    """Unit tests for the validate_custom_field_values function."""

    class FakeDefinition:
        def __init__(self, field_name, field_type, options=None, is_required=False):
            self.field_name = field_name
            self.field_type = field_type
            self.options = options
            self.is_required = is_required

    def test_valid_text_field(self):
        defs = [self.FakeDefinition("name", "text")]
        result = validate_custom_field_values({"name": "hello"}, defs)
        assert result == {"name": "hello"}

    def test_valid_number_field(self):
        defs = [self.FakeDefinition("age", "number")]
        result = validate_custom_field_values({"age": 42}, defs)
        assert result == {"age": 42}

    def test_valid_boolean_field(self):
        defs = [self.FakeDefinition("active", "boolean")]
        result = validate_custom_field_values({"active": True}, defs)
        assert result == {"active": True}

    def test_valid_date_field(self):
        defs = [self.FakeDefinition("birthday", "date")]
        result = validate_custom_field_values({"birthday": "2000-01-15"}, defs)
        assert result == {"birthday": "2000-01-15"}

    def test_valid_dropdown_field(self):
        defs = [self.FakeDefinition("tier", "dropdown", options=["gold", "silver"])]
        result = validate_custom_field_values({"tier": "gold"}, defs)
        assert result == {"tier": "gold"}

    def test_invalid_type_raises(self):
        defs = [self.FakeDefinition("age", "number")]
        with pytest.raises(Exception):
            validate_custom_field_values({"age": "not_a_number"}, defs)

    def test_invalid_dropdown_option_raises(self):
        defs = [self.FakeDefinition("tier", "dropdown", options=["gold", "silver"])]
        with pytest.raises(Exception):
            validate_custom_field_values({"tier": "platinum"}, defs)

    def test_unknown_field_raises(self):
        defs = [self.FakeDefinition("name", "text")]
        with pytest.raises(Exception):
            validate_custom_field_values({"unknown": "value"}, defs)

    def test_required_field_missing_raises(self):
        defs = [self.FakeDefinition("name", "text", is_required=True)]
        with pytest.raises(Exception):
            validate_custom_field_values({}, defs, partial=False)

    def test_required_field_missing_ok_when_partial(self):
        defs = [self.FakeDefinition("name", "text", is_required=True)]
        result = validate_custom_field_values({}, defs, partial=True)
        assert result == {}

    def test_invalid_date_format_raises(self):
        defs = [self.FakeDefinition("birthday", "date")]
        with pytest.raises(Exception):
            validate_custom_field_values({"birthday": "not-a-date"}, defs)

    def test_null_value_ok_for_non_required(self):
        defs = [self.FakeDefinition("name", "text", is_required=False)]
        result = validate_custom_field_values({"name": None}, defs)
        assert result == {"name": None}

    def test_null_value_raises_for_required(self):
        defs = [self.FakeDefinition("name", "text", is_required=True)]
        with pytest.raises(Exception):
            validate_custom_field_values({"name": None}, defs)
