"""
Tests for outbound webhook management endpoints
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from db.models.webhook import WebhookEndpoint


class TestCreateWebhookEndpoint:
    """Tests for POST /api/v1/company/outbound-webhooks"""

    @pytest.mark.asyncio
    async def test_create_endpoint_success(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["lead.created", "call.completed"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["lead.created", "call.completed"]
        assert data["is_active"] is True
        assert "id" in data
        # Secret should not be in response (handled by response model excluding it)

    @pytest.mark.asyncio
    async def test_create_endpoint_invalid_event(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["invalid.event"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_endpoint_short_secret(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/webhook",
                "events": ["lead.created"],
                "secret": "short",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_endpoint_unauthorized(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/company/outbound-webhooks",
            json={
                "url": "https://example.com/webhook",
                "events": ["lead.created"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        assert response.status_code in [401, 403]


class TestListWebhookEndpoints:
    """Tests for GET /api/v1/company/outbound-webhooks"""

    @pytest.mark.asyncio
    async def test_list_endpoints_empty(self, client: AsyncClient, auth_headers):
        response = await client.get(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0
        assert "items" in data

    @pytest.mark.asyncio
    async def test_list_endpoints_with_data(self, client: AsyncClient, auth_headers):
        # Create an endpoint first
        await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/hook",
                "events": ["call.completed"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        response = await client.get(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestGetWebhookEndpoint:
    """Tests for GET /api/v1/company/outbound-webhooks/{id}"""

    @pytest.mark.asyncio
    async def test_get_endpoint(self, client: AsyncClient, auth_headers):
        create_response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/hook",
                "events": ["lead.created"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        endpoint_id = create_response.json()["id"]

        response = await client.get(
            f"/api/v1/company/outbound-webhooks/{endpoint_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["id"] == endpoint_id

    @pytest.mark.asyncio
    async def test_get_endpoint_not_found(self, client: AsyncClient, auth_headers):
        response = await client.get(
            f"/api/v1/company/outbound-webhooks/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestUpdateWebhookEndpoint:
    """Tests for PUT /api/v1/company/outbound-webhooks/{id}"""

    @pytest.mark.asyncio
    async def test_update_endpoint(self, client: AsyncClient, auth_headers):
        create_response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/hook",
                "events": ["lead.created"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        endpoint_id = create_response.json()["id"]

        response = await client.put(
            f"/api/v1/company/outbound-webhooks/{endpoint_id}",
            headers=auth_headers,
            json={
                "url": "https://example.com/new-hook",
                "is_active": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://example.com/new-hook"
        assert data["is_active"] is False


class TestDeleteWebhookEndpoint:
    """Tests for DELETE /api/v1/company/outbound-webhooks/{id}"""

    @pytest.mark.asyncio
    async def test_delete_endpoint(self, client: AsyncClient, auth_headers):
        create_response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/hook",
                "events": ["lead.created"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        endpoint_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/v1/company/outbound-webhooks/{endpoint_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify it's gone
        get_response = await client.get(
            f"/api/v1/company/outbound-webhooks/{endpoint_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


class TestListDeliveries:
    """Tests for GET /api/v1/company/outbound-webhooks/{id}/deliveries"""

    @pytest.mark.asyncio
    async def test_list_deliveries_empty(self, client: AsyncClient, auth_headers):
        create_response = await client.post(
            "/api/v1/company/outbound-webhooks",
            headers=auth_headers,
            json={
                "url": "https://example.com/hook",
                "events": ["lead.created"],
                "secret": "a-very-secure-secret-key-123",
            },
        )
        endpoint_id = create_response.json()["id"]

        response = await client.get(
            f"/api/v1/company/outbound-webhooks/{endpoint_id}/deliveries",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_deliveries_not_found(self, client: AsyncClient, auth_headers):
        response = await client.get(
            f"/api/v1/company/outbound-webhooks/{uuid4()}/deliveries",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestAvailableEvents:
    """Tests for GET /api/v1/company/outbound-webhooks/events"""

    @pytest.mark.asyncio
    async def test_list_events(self, client: AsyncClient, auth_headers):
        response = await client.get(
            "/api/v1/company/outbound-webhooks/events",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "call.completed" in data["events"]
        assert "lead.created" in data["events"]
        assert "deal.stage_changed" in data["events"]
        assert "contact.created" in data["events"]
        assert "call.missed" in data["events"]


class TestWebhookSigning:
    """Tests for HMAC-SHA256 signing utility"""

    def test_sign_payload(self):
        from utils.services.webhook import sign_payload

        payload = b'{"event": "test"}'
        secret = "test-secret"
        signature = sign_payload(payload, secret)

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

    def test_sign_payload_consistency(self):
        from utils.services.webhook import sign_payload

        payload = b'{"event": "test"}'
        secret = "test-secret"

        sig1 = sign_payload(payload, secret)
        sig2 = sign_payload(payload, secret)
        assert sig1 == sig2

    def test_sign_payload_different_secrets(self):
        from utils.services.webhook import sign_payload

        payload = b'{"event": "test"}'
        sig1 = sign_payload(payload, "secret-1")
        sig2 = sign_payload(payload, "secret-2")
        assert sig1 != sig2
