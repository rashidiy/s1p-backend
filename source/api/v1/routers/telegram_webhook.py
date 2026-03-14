"""
Telegram bot webhook endpoint — public, NO authentication.

Receives Telegram updates via POST, routes /start commands to connect
companies by looking up chat_id in TelegramConfig.

Also handles auth flows:
- /start login_{CHALLENGE_ID} — sends OTP for login
- /start reg_{CHALLENGE_ID} — captures Telegram profile for registration
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from aiogram import Bot, Dispatcher, Router as AiogramRouter
from aiogram.filters import CommandStart
from aiogram.types import Update, Message

from core.config import DatabaseConfig, TelegramConfig as TelegramBotConfig
from db.models.telegram_auth_challenge import TelegramAuthChallenge
from db.models.user import User
from utils.services.invite_token_service import generate_otp, hash_token
from utils.services.telegram_service import get_bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telegram Webhook"])

# ── aiogram dispatcher & handler router ──────────────────────────────
tg_router = AiogramRouter()
dp = Dispatcher()
dp.include_router(tg_router)


# ── DB session factory for bot handlers (not in request context) ──────
_bot_engine = None
_bot_session_factory = None


def _get_bot_session_factory():
    """Get a session factory for bot handlers (outside FastAPI request context)."""
    global _bot_engine, _bot_session_factory
    if _bot_session_factory is None:
        _bot_engine = create_async_engine(
            DatabaseConfig.url(),
            future=True,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _bot_session_factory = sessionmaker(
            bind=_bot_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _bot_session_factory


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


# ── /start command handler ───────────────────────────────────────────

@tg_router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """
    Handle /start command.

    - /start (no payload): Show Chat ID for notification setup
    - /start login_{CHALLENGE_ID}: Generate OTP and send to user for login
    """
    text = message.text or ""
    parts = text.strip().split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else ""

    if payload.startswith("login_"):
        await _handle_login_start(message, payload)
        return

    if payload.startswith("reg_"):
        await _handle_register_start(message, payload)
        return

    # Default /start behavior — show Chat ID
    chat_id = message.chat.id
    await message.answer(
        f"S1P CRM Bot connected\\!\n\n"
        f"Your Chat ID: `{chat_id}`\n\n"
        "Copy this Chat ID and paste it in *Settings \\> Telegram* "
        "in the CRM to start receiving notifications\\.",
        parse_mode="MarkdownV2",
    )


def _format_error(text: str) -> str:
    """Format an error message for MarkdownV2."""
    return text


async def _handle_login_start(message: Message, payload: str) -> None:
    """
    Handle /start login_{CHALLENGE_ID} deep link.

    1. Parse challenge ID
    2. Look up challenge (login, not expired, not used)
    3. Find user by telegram_user_id + company_id
    4. Generate OTP, hash it, store in challenge
    5. Send OTP to user via Telegram DM
    """
    from utils.services.telegram_service import _escape_md

    challenge_id = payload[len("login_"):]
    telegram_user_id = message.from_user.id

    session_factory = _get_bot_session_factory()
    async with session_factory() as session:
        try:
            # Look up challenge
            challenge = await session.get(TelegramAuthChallenge, challenge_id)
            now = datetime.now(timezone.utc)

            if (
                not challenge
                or challenge.purpose != "login"
                or challenge.used
            ):
                await message.answer(
                    "Эта ссылка для входа истекла\\. Запросите новую на странице входа\\.",
                    parse_mode="MarkdownV2",
                )
                return

            if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
                await message.answer(
                    "Эта ссылка для входа истекла\\. Запросите новую на странице входа\\.",
                    parse_mode="MarkdownV2",
                )
                return

            # Find user by telegram_user_id + company_id
            user = await User.get(
                session=session,
                telegram_user_id=telegram_user_id,
                company_id=challenge.company_id,
            )
            if not user or user.deleted_at is not None:
                await message.answer(
                    "Аккаунт для этого Telegram не найден в данной компании\\.",
                    parse_mode="MarkdownV2",
                )
                return

            if not user.is_active or user.is_suspended:
                await message.answer(
                    "Ваш аккаунт заблокирован\\. Обратитесь к администратору\\.",
                    parse_mode="MarkdownV2",
                )
                return

            # Check OTP rate limit (1 per 60 seconds per user)
            if await _check_otp_rate_limit(str(user.id)):
                await message.answer(
                    "Подождите перед запросом нового кода\\.",
                    parse_mode="MarkdownV2",
                )
                return

            # Check lockout
            if await _check_otp_lockout(str(user.id)):
                await message.answer(
                    "Аккаунт временно заблокирован\\. Попробуйте позже\\.",
                    parse_mode="MarkdownV2",
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
            await message.answer(
                f"*Код для входа:* `{otp}`\n\n"
                f"_Код действует 5 минут\\. Введите его на странице входа\\._",
                parse_mode="MarkdownV2",
            )

        except Exception:
            logger.exception("Error handling login /start command")
            await message.answer(
                "Произошла ошибка\\. Попробуйте ещё раз\\.",
                parse_mode="MarkdownV2",
            )


async def _handle_register_start(message: Message, payload: str) -> None:
    """
    Handle /start reg_{CHALLENGE_ID} deep link.

    Called from the registration page. The challenge was already created
    by POST /auth/telegram/register-challenge. This handler:
    1. Loads the challenge
    2. Captures Telegram profile data + avatar
    3. Stores telegram_user_id and telegram_data in the challenge
    4. Sends confirmation message
    """
    from utils.services.telegram_service import _escape_md

    challenge_id = payload[len("reg_"):]
    telegram_user_id = message.from_user.id

    session_factory = _get_bot_session_factory()
    async with session_factory() as session:
        try:
            challenge = await session.get(TelegramAuthChallenge, challenge_id)
            now = datetime.now(timezone.utc)

            if not challenge or challenge.purpose != "register":
                await message.answer(
                    "Ссылка недействительна\\.",
                    parse_mode="MarkdownV2",
                )
                return

            if challenge.used:
                await message.answer(
                    "Эта ссылка уже использована\\.",
                    parse_mode="MarkdownV2",
                )
                return

            if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
                await message.answer(
                    "Срок действия ссылки истёк\\.",
                    parse_mode="MarkdownV2",
                )
                return

            # Check if telegram user already registered in this company
            existing = await User.get(
                session=session,
                telegram_user_id=telegram_user_id,
                company_id=challenge.company_id,
            )
            if existing:
                await message.answer(
                    "Этот Telegram аккаунт уже зарегистрирован в этой компании\\.",
                    parse_mode="MarkdownV2",
                )
                return

            # Capture telegram profile data
            tg_user = message.from_user
            telegram_data = {
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
                "username": tg_user.username,
            }

            # Try to get profile photo
            try:
                bot = get_bot()
                if bot:
                    photos = await bot.get_user_profile_photos(user_id=telegram_user_id, limit=1)
                    if photos.total_count > 0 and photos.photos:
                        photo = photos.photos[0][-1]
                        telegram_data["avatar_file_id"] = photo.file_id
            except Exception:
                logger.debug("Could not fetch profile photo for user %s", telegram_user_id)

            # Update challenge with Telegram data
            challenge.telegram_user_id = telegram_user_id
            challenge.telegram_data = telegram_data
            await session.commit()

            # Get company name for confirmation message
            from db.models.company import Company
            company = await session.get(Company, challenge.company_id)
            company_name = company.name if company else "компанию"
            escaped_company = _escape_md(company_name)

            await message.answer(
                f"Telegram подключён\\!\n\n"
                f"Вернитесь на страницу регистрации *{escaped_company}* "
                f"для завершения\\.",
                parse_mode="MarkdownV2",
            )

        except Exception:
            logger.exception("Error handling register /start command")
            await message.answer(
                "Произошла ошибка\\. Попробуйте ещё раз\\.",
                parse_mode="MarkdownV2",
            )


# ── Webhook endpoint ────────────────────────────────────────────────

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    """
    Receive Telegram webhook updates.

    This endpoint is public (no auth). Telegram sends updates here
    when the bot's webhook URL is configured via setWebhook.
    """
    if not TelegramBotConfig.ENABLED:
        return {"status": "disabled"}

    bot = get_bot()
    if not bot:
        return {"status": "no_bot"}

    try:
        body = await request.json()
        update = Update.model_validate(body, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception:
        logger.exception("Error processing Telegram webhook update")

    # Always return 200 to Telegram to prevent retries
    return {"status": "ok"}
