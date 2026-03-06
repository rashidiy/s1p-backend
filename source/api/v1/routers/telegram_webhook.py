"""
Telegram bot webhook endpoint — public, NO authentication.

Receives Telegram updates via POST, routes /start commands to connect
companies by looking up chat_id in TelegramConfig.
"""

import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram import Bot, Dispatcher, Router as AiogramRouter
from aiogram.filters import CommandStart
from aiogram.types import Update, Message

from core.config import TelegramConfig as TelegramBotConfig
from db import get_session
from db.models.telegram_config import TelegramConfig
from utils.services.telegram_service import get_bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telegram Webhook"])

# ── aiogram dispatcher & handler router ──────────────────────────────
tg_router = AiogramRouter()
dp = Dispatcher()
dp.include_router(tg_router)


@tg_router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """
    Handle /start command.

    If the message text contains a deep-link payload (company token),
    it can be used for future auto-connect flows. For now, we just
    acknowledge the connection and tell the admin to use the CRM UI
    to connect this chat.
    """
    chat_id = message.chat.id
    await message.answer(
        f"S1P CRM Bot connected\\!\n\n"
        f"Your Chat ID: `{chat_id}`\n\n"
        "Copy this Chat ID and paste it in *Settings \\> Telegram* "
        "in the CRM to start receiving notifications\\.",
        parse_mode="MarkdownV2",
    )


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
