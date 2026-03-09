"""
Telegram webhook endpoint for receiving bot updates

This endpoint receives callback queries from Telegram when users
press inline keyboard buttons in notification messages.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import TelegramConfig
from db import get_session
from db.models.telegram_config import TelegramBotConfig
from db.models.lead import Lead
from db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/telegram", tags=["Telegram Webhook"])


@router.post("/{secret}")
async def telegram_webhook(
    secret: str,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Receive Telegram bot updates (callback queries from inline buttons).

    Telegram sends JSON updates when users interact with inline keyboards.
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

    # Always return 200 to Telegram
    return {"ok": True}


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
        await _answer_callback(callback_query_id, "⚠️ Бот не настроен для этого чата")
        return

    # Parse callback data: "action:param1:param2"
    parts = callback_data.split(":")
    action = parts[0] if parts else ""

    try:
        if action == "mark_handled":
            await _answer_callback(callback_query_id, "✅ Отмечено как обработанное")

        elif action == "assign_lead" and len(parts) >= 2:
            lead_id = parts[1]
            await _handle_assign_lead(session, config.company_id, lead_id, username)
            await _answer_callback(callback_query_id, "👤 Лид будет назначен")

        elif action == "callback" and len(parts) >= 2:
            phone = parts[1]
            await _answer_callback(callback_query_id, f"📞 Перезвоните на {phone}")

        elif action == "create_contact" and len(parts) >= 2:
            phone = parts[1]
            await _answer_callback(callback_query_id, f"➕ Создайте контакт для {phone} в CRM")

        elif action == "open_contact" and len(parts) >= 2:
            await _answer_callback(callback_query_id, "📋 Откройте контакт в CRM")

        else:
            await _answer_callback(callback_query_id, "⚠️ Неизвестное действие")

    except Exception as e:
        logger.error(f"Error handling callback {action}: {e}", exc_info=True)
        await _answer_callback(callback_query_id, "❌ Ошибка обработки")


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
    from telegram import Bot
    bot_token = TelegramConfig.BOT_TOKEN
    if not bot_token:
        return

    try:
        bot = Bot(token=bot_token)
        await bot.answer_callback_query(callback_query_id=callback_query_id, text=text)
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}", exc_info=True)
