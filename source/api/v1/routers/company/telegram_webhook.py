"""
Telegram webhook endpoint for receiving bot updates

This endpoint receives all Telegram bot updates:
- Callback queries from inline keyboard buttons
- Messages including /start and /register commands for auth flows
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import AppConfig, TelegramConfig
from db import get_session
from db.models.telegram_config import TelegramBotConfig
from db.models.telegram_auth_challenge import TelegramAuthChallenge
from db.models.lead import Lead
from db.models.user import User
from utils.services.invite_token_service import generate_otp, hash_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/telegram", tags=["Telegram Webhook"])


# ── Bot instance for sending messages ─────────────────────────────────

def _get_bot() -> Bot | None:
    """Get an aiogram Bot instance for sending messages."""
    if not TelegramConfig.BOT_TOKEN:
        return None
    return Bot(token=TelegramConfig.BOT_TOKEN)


# ── Redis helpers for OTP rate limiting ──────────────────────────────

async def _get_redis():
    """Get Redis client for OTP rate limiting."""
    try:
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    except Exception:
        return None


async def _check_otp_rate_limit(user_id: str) -> bool:
    """Check if an OTP was sent for this user in the last 60 seconds."""
    client = await _get_redis()
    if not client:
        return False
    val = await client.get(f"otp_rate:{user_id}")
    return val is not None


async def _set_otp_rate_limit(user_id: str) -> None:
    """Set OTP rate limit key (60s TTL)."""
    client = await _get_redis()
    if not client:
        return
    await client.setex(f"otp_rate:{user_id}", 60, "1")


async def _check_otp_lockout(user_id: str) -> bool:
    """Check if user is locked out from OTP verification."""
    client = await _get_redis()
    if not client:
        return False
    val = await client.get(f"otp_lockout:{user_id}")
    return val is not None


# ── Webhook endpoint ─────────────────────────────────────────────────

@router.post("/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Receive Telegram bot updates.

    Handles:
    - Callback queries (inline button presses)
    - Messages (/start, /register commands for auth flows)

    The secret path parameter validates the webhook is from our bot setup.
    """
    # Validate webhook secret
    if not TelegramConfig.WEBHOOK_SECRET or secret != TelegramConfig.WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret"
        )

    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    # Handle callback queries (button presses)
    callback_query = data.get("callback_query")
    if callback_query:
        await _handle_callback_query(callback_query, session)

    # Handle messages (commands)
    message = data.get("message")
    if message:
        await _handle_message(message, session)

    # Always return 200 to Telegram
    return {"ok": True}


# ── Message handlers ─────────────────────────────────────────────────

async def _handle_message(message: dict, session: AsyncSession):
    """Route incoming messages to the appropriate handler."""
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")

    if not text or not chat_id or not telegram_user_id:
        return

    try:
        if text.startswith("/start"):
            parts = text.strip().split(maxsplit=1)
            payload = parts[1] if len(parts) > 1 else ""

            if payload.startswith("login_"):
                await _handle_login_start(chat_id, telegram_user_id, payload, session)
            else:
                # Default /start — show Chat ID
                await _send_message(
                    chat_id,
                    f"S1P CRM Bot connected!\n\n"
                    f"Your Chat ID: {chat_id}\n\n"
                    f"Copy this Chat ID and paste it in Settings > Telegram "
                    f"in the CRM to start receiving notifications."
                )

        elif text.startswith("/register"):
            await _handle_register(chat_id, telegram_user_id, session)

    except Exception:
        logger.exception("Error handling message from Telegram user %s", telegram_user_id)


async def _handle_login_start(
    chat_id: int,
    telegram_user_id: int,
    payload: str,
    session: AsyncSession,
) -> None:
    """
    Handle /start login_{CHALLENGE_ID} deep link.

    1. Parse challenge ID
    2. Look up challenge (login, not expired, not used)
    3. Find user by telegram_user_id + company_id
    4. Generate OTP, hash it, store in challenge
    5. Send OTP to user via Telegram DM
    """
    challenge_id = payload[len("login_"):]
    now = datetime.now(timezone.utc)

    # Look up challenge
    challenge = await session.get(TelegramAuthChallenge, challenge_id)

    if (
        not challenge
        or challenge.purpose != "login"
        or challenge.used
    ):
        await _send_message(
            chat_id,
            "This login link has expired. Please request a new one from the login page."
        )
        return

    if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        await _send_message(
            chat_id,
            "This login link has expired. Please request a new one from the login page."
        )
        return

    # Find user by telegram_user_id + company_id
    user = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=challenge.company_id,
    )
    if not user or user.deleted_at is not None:
        await _send_message(
            chat_id,
            "No account found for this Telegram account in this company."
        )
        return

    if not user.is_active or user.is_suspended:
        await _send_message(
            chat_id,
            "Your account is suspended. Contact your administrator."
        )
        return

    # Check OTP rate limit (1 per 60 seconds per user)
    if await _check_otp_rate_limit(str(user.id)):
        await _send_message(
            chat_id,
            "Please wait before requesting another code."
        )
        return

    # Check lockout
    if await _check_otp_lockout(str(user.id)):
        await _send_message(
            chat_id,
            "Account temporarily locked. Try again later."
        )
        return

    # Generate OTP
    otp = generate_otp()
    otp_hashed = hash_token(otp)

    # Update challenge
    challenge.telegram_user_id = telegram_user_id
    challenge.user_id = user.id
    challenge.otp_hash = otp_hashed
    challenge.expires_at = now + timedelta(minutes=5)

    await session.commit()

    # Set rate limit
    await _set_otp_rate_limit(str(user.id))

    # Send OTP to user
    await _send_message(
        chat_id,
        f"Your login code: {otp}\n\n"
        f"This code expires in 5 minutes. Enter it on the login page."
    )


async def _handle_register(
    chat_id: int,
    telegram_user_id: int,
    session: AsyncSession,
) -> None:
    """
    Handle /register command.

    Creates a registration challenge and sends the user a link
    to the registration page on the website.
    """
    now = datetime.now(timezone.utc)
    challenge_id = secrets.token_urlsafe(16)

    challenge = TelegramAuthChallenge(
        id=challenge_id,
        company_id=None,  # Resolved from invite token at registration
        purpose="register",
        telegram_user_id=telegram_user_id,
        expires_at=now + timedelta(minutes=10),
    )
    session.add(challenge)
    await session.commit()

    # Build registration link
    base_url = AppConfig.FRONTEND_URL.rstrip("/")
    reg_url = f"{base_url}/auth/register?s={challenge_id}"

    await _send_message(
        chat_id,
        f"To complete registration, open this link and enter your invite code:\n\n"
        f"{reg_url}"
    )


# ── Send message helper ──────────────────────────────────────────────

async def _send_message(chat_id: int, text: str) -> None:
    """Send a plain text message to a Telegram chat."""
    bot = _get_bot()
    if not bot:
        return

    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.exception("Failed to send Telegram message to chat %s", chat_id)
    finally:
        await bot.session.close()


# ── Callback query handlers (existing) ───────────────────────────────

async def _handle_callback_query(callback_query: dict, session: AsyncSession):
    """Process inline button callback queries."""
    callback_data = callback_query.get("data", "")
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    callback_query_id = callback_query.get("id")
    user_info = callback_query.get("from", {})
    username = user_info.get("username", "unknown")

    if not callback_data or not chat_id:
        return

    # Find company by chat_id
    result = await session.execute(
        select(TelegramBotConfig).where(
            TelegramBotConfig.chat_id == chat_id,
            TelegramBotConfig.enabled.is_(True),
            TelegramBotConfig.deleted_at.is_(None)
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        await _answer_callback(callback_query_id, "Bot not configured for this chat")
        return

    # Parse callback data: "action:param1:param2"
    parts = callback_data.split(":")
    action = parts[0] if parts else ""

    try:
        if action == "mark_handled":
            await _answer_callback(callback_query_id, "Marked as handled")

        elif action == "assign_lead" and len(parts) >= 2:
            lead_id = parts[1]
            await _handle_assign_lead(session, config.company_id, lead_id, username)
            await _answer_callback(callback_query_id, "Lead will be assigned")

        elif action == "callback" and len(parts) >= 2:
            phone = parts[1]
            await _answer_callback(callback_query_id, f"Call back {phone}")

        elif action == "create_contact" and len(parts) >= 2:
            phone = parts[1]
            await _answer_callback(callback_query_id, f"Create contact for {phone} in CRM")

        elif action == "open_contact" and len(parts) >= 2:
            await _answer_callback(callback_query_id, "Open contact in CRM")

        else:
            await _answer_callback(callback_query_id, "Unknown action")

    except Exception as e:
        logger.error(f"Error handling callback {action}: {e}", exc_info=True)
        await _answer_callback(callback_query_id, "Error processing request")


async def _handle_assign_lead(session: AsyncSession, company_id, lead_id: str, username: str):
    """Handle lead assignment from Telegram button."""
    try:
        lead = await Lead.get(
            session=session,
            id=lead_id,
            company_id=company_id
        )
        if lead and not lead.assigned_to:
            # Log the assignment request — actual assignment needs a CRM user
            logger.info(f"Lead {lead_id} assignment requested by Telegram user @{username}")
    except Exception as e:
        logger.error(f"Failed to handle lead assignment: {e}", exc_info=True)


async def _answer_callback(callback_query_id: str, text: str):
    """Answer a Telegram callback query."""
    bot = _get_bot()
    if not bot:
        return

    try:
        await bot.answer_callback_query(callback_query_id=callback_query_id, text=text)
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}", exc_info=True)
    finally:
        await bot.session.close()
