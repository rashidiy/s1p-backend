"""
Tests for unified telephony webhook handler
"""

import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.company import Company
from db.models.enums import ProviderEnum


WEBHOOK_PREFIX = "/api/v1/company/webhooks"


class TestWebhookTokenValidation:
    """Webhook token lookup and validation"""

    @pytest.mark.asyncio
    async def test_invalid_token_returns_404(self, client: AsyncClient):
        """Unknown webhook token returns 404."""
        response = await client.get(f"{WEBHOOK_PREFIX}/nonexistent-token")
        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    @patch("api.v1.routers.company.webhooks._send_call_notification", new_callable=AsyncMock)
    @patch("api.v1.routers.company.webhooks._fire_call_webhook", new_callable=AsyncMock)
    @patch("api.v1.routers.company.webhooks.next_call_number", new_callable=AsyncMock)
    async def test_valid_token_resolves_company(
        self, mock_next_id, mock_fire, mock_notify, mock_factory, mock_ip,
        client: AsyncClient, test_company
    ):
        """Valid webhook token finds the company."""
        import random
        mock_next_id.return_value = random.randint(9_000_000, 9_999_999)

        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value={
            "provider_call_id": f"call_{uuid.uuid4().hex[:8]}",
            "phone_1": "+1234567890",
            "phone_2": "+0987654321",
            "state": "ANSWER",
        })
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"provider_call_id": "call_001"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("created", "updated")


class TestWebhookIPValidation:
    """IP whitelist validation"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=False)
    async def test_blocked_ip_returns_403(
        self, mock_ip, client: AsyncClient, test_company
    ):
        """Request from non-whitelisted IP is rejected."""
        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"provider_call_id": "call_001"},
        )
        assert response.status_code == 403


class TestWebhookAuthValidation:
    """Provider-specific auth validation"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    async def test_failed_auth_returns_403(
        self, mock_factory, mock_ip, client: AsyncClient, test_company
    ):
        """Failed provider auth returns 403."""
        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=False)
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"some": "data"},
        )
        assert response.status_code == 403


class TestWebhookCallProcessing:
    """Call event creation and updates"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    @patch("api.v1.routers.company.webhooks._send_call_notification", new_callable=AsyncMock)
    @patch("api.v1.routers.company.webhooks._fire_call_webhook", new_callable=AsyncMock)
    @patch("api.v1.routers.company.webhooks.next_call_number", new_callable=AsyncMock)
    async def test_creates_new_call_event(
        self, mock_next_id, mock_fire, mock_notify, mock_factory, mock_ip,
        client: AsyncClient, test_company
    ):
        """Creates a new call event for unknown provider_call_id."""
        import random
        mock_next_id.return_value = random.randint(9_000_000, 9_999_999)

        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value={
            "provider_call_id": f"new_call_{uuid.uuid4().hex[:8]}",
            "phone_1": "+1234567890",
            "phone_2": "+0987654321",
            "state": "ANSWER",
            "billing_sec": 120,
        })
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"event": "call"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert "call_id" in data

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    async def test_ignored_event_type(
        self, mock_factory, mock_ip, client: AsyncClient, test_company
    ):
        """Provider returns None for non-call events → ignored."""
        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value=None)
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"event": "something_else"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    async def test_malformed_call_data_returns_422(
        self, mock_factory, mock_ip, client: AsyncClient, test_company
    ):
        """Invalid/extra fields in normalized data cause 422."""
        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value={
            "provider_call_id": "call_bad",
            "unexpected_extra_field": "should fail",
        })
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"event": "call"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    @patch("api.v1.routers.company.webhooks._send_call_notification", new_callable=AsyncMock)
    @patch("api.v1.routers.company.webhooks._fire_call_webhook", new_callable=AsyncMock)
    async def test_updates_existing_call_event(
        self, mock_fire, mock_notify, mock_factory, mock_ip,
        client: AsyncClient, test_company, test_call_event
    ):
        """Updates an existing call event when provider_call_id matches."""
        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value={
            "provider_call_id": test_call_event.provider_call_id,
            "state": "ANSWER",
            "billing_sec": 300,
        })
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"event": "update"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["call_id"] == test_call_event.id


class TestWebhookMultiTenancy:
    """Multi-tenancy: webhook creates data only for the correct company"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.webhooks.validate_webhook_ip", return_value=True)
    @patch("api.v1.routers.company.webhooks.ProviderFactory")
    async def test_entity_ownership_validation(
        self, mock_factory, mock_ip, client: AsyncClient, test_company, active_user
    ):
        """Cannot reference an operator from another company."""
        mock_provider = AsyncMock()
        mock_provider.validate_webhook_auth = AsyncMock(return_value=True)
        mock_provider.handle_webhook = AsyncMock(return_value={
            "provider_call_id": f"call_{uuid.uuid4().hex[:8]}",
            "phone_1": "+1234567890",
            "operator_id": str(active_user.id),  # User from another company
        })
        mock_factory.create.return_value = mock_provider

        response = await client.get(
            f"{WEBHOOK_PREFIX}/{test_company.webhook_token}",
            params={"event": "call"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_other_company_token_not_found(
        self, client: AsyncClient, active_user, db_session
    ):
        """Using a random token that doesn't match any company returns 404."""
        response = await client.get(f"{WEBHOOK_PREFIX}/{uuid.uuid4()}")
        assert response.status_code == 404
