"""
Tests for Telegram bot configuration endpoints
"""

import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.telegram_config import TelegramBotConfig


TELEGRAM_PREFIX = "/api/v1/company/telegram"


@pytest.fixture
async def telegram_config(db_session: AsyncSession, test_company):
    """Create a TelegramBotConfig for the test company."""
    config = TelegramBotConfig(
        id=uuid.uuid4(),
        company_id=test_company.id,
        chat_id="123456789",
        enabled=True,
        notification_filters={
            "call_completed": True,
            "call_missed": True,
            "new_lead": True,
            "deal_stage_change": False,
        },
        setup_status="not_started",
        language="ru",
        send_recordings=True,
        daily_digest=True,
        dm_notifications=False,
    )
    db_session.add(config)
    await db_session.flush()
    return config


class TestGetTelegramConfig:
    """Tests for GET /company/telegram/config"""

    @pytest.mark.asyncio
    async def test_get_config_success(self, client: AsyncClient, auth_headers, telegram_config):
        """Returns config when it exists."""
        response = await client.get(f"{TELEGRAM_PREFIX}/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == "123456789"
        assert data["bot_enabled"] is True
        assert data["notify_completed_calls"] is True
        assert data["notify_deal_stage_change"] is False

    @pytest.mark.asyncio
    async def test_get_config_not_found(self, client: AsyncClient, auth_headers):
        """Returns 404 when no config exists."""
        response = await client.get(f"{TELEGRAM_PREFIX}/config", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_operator_forbidden(self, client: AsyncClient, operator_auth_headers):
        """Operator without settings.read cannot get config."""
        response = await client.get(f"{TELEGRAM_PREFIX}/config", headers=operator_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_config_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request fails."""
        response = await client.get(f"{TELEGRAM_PREFIX}/config")
        assert response.status_code in [401, 403]


class TestCreateTelegramConfig:
    """Tests for POST /company/telegram/config"""

    @pytest.mark.asyncio
    async def test_create_config_success(self, client: AsyncClient, auth_headers):
        """Admin can create a new config."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={
                "chat_id": "987654321",
                "bot_enabled": True,
                "notify_completed_calls": True,
                "notify_missed_calls": False,
                "notify_new_leads": True,
                "notify_deal_stage_change": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["chat_id"] == "987654321"
        assert data["bot_enabled"] is True
        assert data["notify_missed_calls"] is False

    @pytest.mark.asyncio
    async def test_create_config_upserts_existing(
        self, client: AsyncClient, auth_headers, telegram_config
    ):
        """Creating when config exists updates the existing one."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={
                "chat_id": "111222333",
                "bot_enabled": False,
                "notify_completed_calls": False,
                "notify_missed_calls": False,
                "notify_new_leads": False,
                "notify_deal_stage_change": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["chat_id"] == "111222333"
        assert data["bot_enabled"] is False

    @pytest.mark.asyncio
    async def test_create_config_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot create config (requires settings.manage)."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/config",
            headers=operator_auth_headers,
            json={"chat_id": "999"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_config_missing_chat_id(self, client: AsyncClient, auth_headers):
        """Missing required chat_id fails validation."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={"bot_enabled": True},
        )
        assert response.status_code == 422


class TestUpdateTelegramConfig:
    """Tests for PUT /company/telegram/config"""

    @pytest.mark.asyncio
    async def test_update_config_toggle_notifications(
        self, client: AsyncClient, auth_headers, telegram_config
    ):
        """Can toggle individual notification settings."""
        response = await client.put(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={
                "notify_missed_calls": False,
                "notify_deal_stage_change": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["notify_missed_calls"] is False
        assert data["notify_deal_stage_change"] is True
        # Unchanged fields should remain
        assert data["notify_completed_calls"] is True

    @pytest.mark.asyncio
    async def test_update_config_disable_bot(
        self, client: AsyncClient, auth_headers, telegram_config
    ):
        """Can disable the bot."""
        response = await client.put(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={"bot_enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["bot_enabled"] is False

    @pytest.mark.asyncio
    @patch("utils.services.telegram_service.TelegramService.rename_forum_topics", new_callable=AsyncMock)
    async def test_update_config_language_change(
        self, mock_rename, client: AsyncClient, auth_headers, telegram_config, db_session
    ):
        """Changing language triggers topic rename (when topics exist)."""
        # Give config topics and a group_chat_id so the rename path triggers
        telegram_config.topic_ids = {"calls": 10, "leads": 12}
        telegram_config.group_chat_id = -1001234567890
        await db_session.flush()

        response = await client.put(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={"language": "en"},
        )
        assert response.status_code == 200
        assert response.json()["language"] == "en"

    @pytest.mark.asyncio
    async def test_update_config_not_found(self, client: AsyncClient, auth_headers):
        """Update when no config exists returns 404."""
        response = await client.put(
            f"{TELEGRAM_PREFIX}/config",
            headers=auth_headers,
            json={"bot_enabled": False},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_config_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot update config."""
        response = await client.put(
            f"{TELEGRAM_PREFIX}/config",
            headers=operator_auth_headers,
            json={"bot_enabled": False},
        )
        assert response.status_code == 403


class TestDeleteTelegramConfig:
    """Tests for DELETE /company/telegram/config"""

    @pytest.mark.asyncio
    @patch("utils.services.pyrogram_service.is_available", return_value=False)
    async def test_delete_config_success(
        self, mock_pyro, client: AsyncClient, auth_headers, telegram_config
    ):
        """Admin can delete config."""
        response = await client.delete(f"{TELEGRAM_PREFIX}/config", headers=auth_headers)
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, client: AsyncClient, auth_headers):
        """Delete when no config exists returns 404."""
        response = await client.delete(f"{TELEGRAM_PREFIX}/config", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_config_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot delete config."""
        response = await client.delete(f"{TELEGRAM_PREFIX}/config", headers=operator_auth_headers)
        assert response.status_code == 403


class TestSendTestMessage:
    """Tests for POST /company/telegram/test"""

    @pytest.mark.asyncio
    @patch(
        "utils.services.telegram_service.TelegramService.send_test_message",
        new_callable=AsyncMock,
        return_value=True,
    )
    async def test_send_test_success(
        self, mock_send, client: AsyncClient, auth_headers, telegram_config
    ):
        """Sends test message successfully."""
        response = await client.post(f"{TELEGRAM_PREFIX}/test", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    @patch(
        "utils.services.telegram_service.TelegramService.send_test_message",
        new_callable=AsyncMock,
        return_value=False,
    )
    async def test_send_test_failure(
        self, mock_send, client: AsyncClient, auth_headers, telegram_config
    ):
        """Returns 502 when sending fails."""
        response = await client.post(f"{TELEGRAM_PREFIX}/test", headers=auth_headers)
        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_send_test_no_config(self, client: AsyncClient, auth_headers):
        """Returns 404 when no config exists."""
        response = await client.post(f"{TELEGRAM_PREFIX}/test", headers=auth_headers)
        assert response.status_code == 404


class TestSetupStatus:
    """Tests for GET /company/telegram/setup/status"""

    @pytest.mark.asyncio
    async def test_setup_status_not_started(self, client: AsyncClient, auth_headers):
        """Returns not_started when no config exists."""
        response = await client.get(f"{TELEGRAM_PREFIX}/setup/status", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["setup_status"] == "not_started"

    @pytest.mark.asyncio
    async def test_setup_status_with_config(
        self, client: AsyncClient, auth_headers, telegram_config, db_session
    ):
        """Returns current status from config."""
        telegram_config.setup_status = "ready"
        telegram_config.invite_link = "https://t.me/+abc"
        telegram_config.group_name = "S1P — Test"
        await db_session.flush()

        response = await client.get(f"{TELEGRAM_PREFIX}/setup/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["setup_status"] == "ready"
        assert data["invite_link"] == "https://t.me/+abc"
        assert data["group_name"] == "S1P — Test"


class TestManualSetup:
    """Tests for POST /company/telegram/setup/manual"""

    @pytest.mark.asyncio
    @patch(
        "utils.services.telegram_service.TelegramService.create_forum_topics",
        new_callable=AsyncMock,
        return_value={"calls": 10, "leads": 12, "deals": 13, "general": 1},
    )
    async def test_manual_setup_success(self, mock_topics, client: AsyncClient, auth_headers):
        """Manual setup creates config with topics."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/setup/manual",
            headers=auth_headers,
            json={"chat_id": "-1001234567890"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["setup_status"] == "ready"

    @pytest.mark.asyncio
    @patch(
        "utils.services.telegram_service.TelegramService.create_forum_topics",
        new_callable=AsyncMock,
        side_effect=Exception("Forbidden: not enough rights"),
    )
    async def test_manual_setup_topic_failure_fallback(
        self, mock_topics, client: AsyncClient, auth_headers
    ):
        """Falls back to manual status when topic creation fails."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/setup/manual",
            headers=auth_headers,
            json={"chat_id": "-1001234567890"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["setup_status"] == "manual"
        assert data["setup_error"] is not None

    @pytest.mark.asyncio
    async def test_manual_setup_operator_forbidden(
        self, client: AsyncClient, operator_auth_headers
    ):
        """Operator cannot run manual setup."""
        response = await client.post(
            f"{TELEGRAM_PREFIX}/setup/manual",
            headers=operator_auth_headers,
            json={"chat_id": "-100"},
        )
        assert response.status_code == 403


class TestTelegramMultiTenancy:
    """Multi-tenancy isolation for telegram config"""

    @pytest.mark.asyncio
    async def test_cannot_see_other_company_config(
        self, client: AsyncClient, auth_headers, active_auth_headers, telegram_config
    ):
        """Company B cannot see Company A's telegram config."""
        # Company A has config
        resp_a = await client.get(f"{TELEGRAM_PREFIX}/config", headers=auth_headers)
        assert resp_a.status_code == 200

        # Company B should get 404
        resp_b = await client.get(f"{TELEGRAM_PREFIX}/config", headers=active_auth_headers)
        assert resp_b.status_code == 404
