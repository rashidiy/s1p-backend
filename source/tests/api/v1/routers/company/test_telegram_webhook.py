"""
Tests for Telegram webhook endpoint (receives bot updates)
"""

import pytest
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.telegram_config import TelegramBotConfig
from db.models.telegram_auth_challenge import TelegramAuthChallenge
from db.models.user import User
from db.models.enums import RoleEnum


WEBHOOK_PREFIX = "/api/v1/webhooks/telegram"


@pytest.fixture
def webhook_secret():
    return "test-webhook-secret-abc123"


@pytest.fixture
async def tg_config(db_session: AsyncSession, test_company):
    """Telegram config linked to test company."""
    config = TelegramBotConfig(
        id=uuid.uuid4(),
        company_id=test_company.id,
        chat_id="-1001111111111",
        group_chat_id=-1001111111111,
        enabled=True,
        notification_filters={
            "call_completed": True,
            "call_missed": True,
            "new_lead": True,
            "deal_stage_change": False,
        },
        setup_status="ready",
        language="en",
    )
    db_session.add(config)
    await db_session.flush()
    return config


@pytest.fixture
async def linked_user(db_session: AsyncSession, test_company):
    """A user with telegram_user_id linked."""
    from utils.managers import PasswordManager

    user = User(
        id=uuid.uuid4(),
        company_id=test_company.id,
        email=f"tguser_{uuid.uuid4().hex[:8]}@test.com",
        password_hash=PasswordManager.hash("testpassword123"),
        first_name="Telegram",
        last_name="User",
        phone="+1112223344",
        role=RoleEnum.COMPANY_ADMIN,
        permissions=["*"],
        is_active=True,
        email_verified=True,
        telegram_user_id=777888999,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def login_challenge(db_session: AsyncSession, test_company):
    """An active login challenge."""
    challenge = TelegramAuthChallenge(
        id=secrets.token_urlsafe(16),
        company_id=test_company.id,
        purpose="login",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used=False,
    )
    db_session.add(challenge)
    await db_session.flush()
    return challenge


@pytest.fixture
async def register_challenge(db_session: AsyncSession, test_company):
    """An active register challenge."""
    challenge = TelegramAuthChallenge(
        id=secrets.token_urlsafe(16),
        company_id=test_company.id,
        purpose="register",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        used=False,
    )
    db_session.add(challenge)
    await db_session.flush()
    return challenge


def _make_update(message: dict = None, callback_query: dict = None) -> dict:
    """Build a minimal Telegram Update payload."""
    update = {"update_id": 12345}
    if message:
        update["message"] = message
    if callback_query:
        update["callback_query"] = callback_query
    return update


def _make_message(chat_id: int, text: str, user_id: int = 777888999) -> dict:
    return {
        "message_id": 1,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "first_name": "Test", "username": "testuser"},
        "text": text,
        "date": 1700000000,
    }


class TestWebhookSecretValidation:
    """Webhook secret validation"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    async def test_invalid_secret_returns_403(self, mock_cfg, client: AsyncClient):
        """Invalid webhook secret is rejected."""
        mock_cfg.WEBHOOK_SECRET = "real-secret"
        mock_cfg.BOT_TOKEN = "fake:token"
        response = await client.post(
            f"{WEBHOOK_PREFIX}/wrong-secret",
            json=_make_update(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    async def test_valid_secret_returns_200(self, mock_cfg, client: AsyncClient, webhook_secret):
        """Valid secret is accepted."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(),
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    async def test_empty_secret_config_rejects_all(self, mock_cfg, client: AsyncClient):
        """When WEBHOOK_SECRET is empty, all requests are rejected."""
        mock_cfg.WEBHOOK_SECRET = ""
        mock_cfg.BOT_TOKEN = ""
        response = await client.post(
            f"{WEBHOOK_PREFIX}/any-secret",
            json=_make_update(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    async def test_malformed_json_returns_ok(self, mock_cfg, client: AsyncClient, webhook_secret):
        """Malformed JSON body still returns 200 (Telegram expects this)."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200


class TestStartCommand:
    """Tests for /start deep link handling"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_start_plain_shows_chat_id(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret
    ):
        """Plain /start shows the chat ID."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = "fake:token"
        msg = _make_message(chat_id=12345, text="/start")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "12345" in sent_text

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    @patch("api.v1.routers.company.telegram_webhook._check_otp_rate_limit", new_callable=AsyncMock, return_value=False)
    @patch("api.v1.routers.company.telegram_webhook._check_otp_lockout", new_callable=AsyncMock, return_value=False)
    @patch("api.v1.routers.company.telegram_webhook._set_otp_rate_limit", new_callable=AsyncMock)
    async def test_start_login_sends_otp(
        self,
        mock_set_rate,
        mock_lockout,
        mock_rate,
        mock_send,
        mock_cfg,
        client: AsyncClient,
        webhook_secret,
        login_challenge,
        linked_user,
    ):
        """Login deep link sends OTP to linked user."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""  # Prevents actual bot calls
        msg = _make_message(
            chat_id=99999,
            text=f"/start login_{login_challenge.id}",
            user_id=linked_user.telegram_user_id,
        )
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        # Should have sent OTP message
        assert mock_send.call_count >= 1
        last_call_text = mock_send.call_args[0][1]
        assert "code" in last_call_text.lower() or "expires" in last_call_text.lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_start_login_expired_challenge(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret, db_session, test_company
    ):
        """Expired login challenge shows error."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""

        expired = TelegramAuthChallenge(
            id=secrets.token_urlsafe(16),
            company_id=test_company.id,
            purpose="login",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            used=False,
        )
        db_session.add(expired)
        await db_session.flush()

        msg = _make_message(chat_id=99999, text=f"/start login_{expired.id}")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "expired" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_start_login_unknown_user(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret, login_challenge
    ):
        """Login with unlinked telegram user shows error."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(
            chat_id=99999,
            text=f"/start login_{login_challenge.id}",
            user_id=999999999,  # Unknown telegram user
        )
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "no account" in mock_send.call_args[0][1].lower()


class TestRegisterFlow:
    """Tests for /start reg_ deep link handling"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    @patch("api.v1.routers.company.telegram_webhook._get_bot", return_value=None)
    async def test_register_start_captures_data(
        self, mock_bot, mock_send, mock_cfg, client: AsyncClient, webhook_secret, register_challenge
    ):
        """Register deep link captures telegram profile data."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(
            chat_id=55555,
            text=f"/start reg_{register_challenge.id}",
            user_id=111222333,
        )
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "connected" in mock_send.call_args[0][1].lower() or "registration" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_register_start_expired(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret, db_session, test_company
    ):
        """Expired register challenge shows error."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""

        expired = TelegramAuthChallenge(
            id=secrets.token_urlsafe(16),
            company_id=test_company.id,
            purpose="register",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            used=False,
        )
        db_session.add(expired)
        await db_session.flush()

        msg = _make_message(chat_id=55555, text=f"/start reg_{expired.id}")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "expired" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    @patch("api.v1.routers.company.telegram_webhook._get_bot", return_value=None)
    async def test_register_start_already_registered(
        self, mock_bot, mock_send, mock_cfg, client: AsyncClient, webhook_secret,
        register_challenge, linked_user
    ):
        """Already-registered telegram user gets rejection."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(
            chat_id=55555,
            text=f"/start reg_{register_challenge.id}",
            user_id=linked_user.telegram_user_id,
        )
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "already registered" in mock_send.call_args[0][1].lower()


class TestBotCommands:
    """Tests for /today, /search, /myleads commands"""

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_today_no_config(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret
    ):
        """Today command in unconfigured chat shows error."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(chat_id=99999, text="/today")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "not configured" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_search_no_query(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret
    ):
        """Search without query shows usage."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(chat_id=99999, text="/search")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "usage" in mock_send.call_args[0][1].lower()

    @pytest.mark.asyncio
    @patch("api.v1.routers.company.telegram_webhook.TelegramConfig")
    @patch("api.v1.routers.company.telegram_webhook._send_message", new_callable=AsyncMock)
    async def test_myleads_no_config(
        self, mock_send, mock_cfg, client: AsyncClient, webhook_secret
    ):
        """Myleads in unconfigured chat shows error."""
        mock_cfg.WEBHOOK_SECRET = webhook_secret
        mock_cfg.BOT_TOKEN = ""
        msg = _make_message(chat_id=99999, text="/myleads")
        response = await client.post(
            f"{WEBHOOK_PREFIX}/{webhook_secret}",
            json=_make_update(message=msg),
        )
        assert response.status_code == 200
        mock_send.assert_called_once()
        assert "not configured" in mock_send.call_args[0][1].lower()
