"""
Telegram notification service

Sends CRM event notifications to company Telegram chats.
Uses python-telegram-bot for message formatting and delivery.
All sending happens in background tasks — never blocks the request.
"""

import logging
from typing import Optional
from uuid import UUID

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import TelegramConfig
from db.models.telegram_config import TelegramBotConfig

logger = logging.getLogger(__name__)


def _get_bot() -> Optional[Bot]:
    """Get shared bot instance. Returns None if not configured."""
    if not TelegramConfig.BOT_TOKEN or not TelegramConfig.ENABLED:
        return None
    return Bot(token=TelegramConfig.BOT_TOKEN)


async def _get_config(session: AsyncSession, company_id: UUID) -> Optional[TelegramBotConfig]:
    """Get TelegramBotConfig for a company."""
    result = await session.execute(
        select(TelegramBotConfig).where(
            TelegramBotConfig.company_id == company_id,
            TelegramBotConfig.enabled.is_(True),
            TelegramBotConfig.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


class TelegramService:
    """Service for sending Telegram notifications for CRM events."""

    @staticmethod
    async def notify_call_completed(
        session: AsyncSession,
        company_id: UUID,
        caller_phone: str,
        operator_name: Optional[str],
        duration_sec: int,
        contact_name: Optional[str] = None,
        contact_id: Optional[UUID] = None,
        record_url: Optional[str] = None,
        direction: str = "inbound",
    ):
        """Send notification for completed call."""
        config = await _get_config(session, company_id)
        if not config or not config.is_event_enabled("call_completed"):
            return

        bot = _get_bot()
        if not bot:
            return

        try:
            # Format message
            direction_icon = "📞" if direction == "inbound" else "📱"
            direction_text = "Входящий" if direction == "inbound" else "Исходящий"

            lines = [
                f"{direction_icon} <b>Звонок завершён</b>",
                "",
                f"📲 <b>Номер:</b> {caller_phone}",
            ]

            if contact_name:
                lines.append(f"👤 <b>Контакт:</b> {contact_name}")

            if operator_name:
                lines.append(f"🧑‍💼 <b>Оператор:</b> {operator_name}")

            lines.append(f"⏱ <b>Длительность:</b> {_format_duration(duration_sec)}")
            lines.append(f"↕️ <b>Направление:</b> {direction_text}")

            if record_url:
                lines.append(f"🎙 <a href=\"{record_url}\">Запись разговора</a>")

            text = "\n".join(lines)

            # Buttons
            buttons = []
            if contact_id:
                buttons.append([
                    InlineKeyboardButton("📋 Открыть контакт", callback_data=f"open_contact:{contact_id}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton("➕ Создать контакт", callback_data=f"create_contact:{caller_phone}")
                ])

            buttons.append([
                InlineKeyboardButton("✅ Обработано", callback_data=f"mark_handled:call_completed:{caller_phone}")
            ])

            reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send call_completed notification: {e}", exc_info=True)

    @staticmethod
    async def notify_call_missed(
        session: AsyncSession,
        company_id: UUID,
        caller_phone: str,
        operator_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_id: Optional[UUID] = None,
    ):
        """Send notification for missed call."""
        config = await _get_config(session, company_id)
        if not config or not config.is_event_enabled("call_missed"):
            return

        bot = _get_bot()
        if not bot:
            return

        try:
            lines = [
                "🔴 <b>Пропущенный звонок!</b>",
                "",
                f"📲 <b>Номер:</b> {caller_phone}",
            ]

            if contact_name:
                lines.append(f"👤 <b>Контакт:</b> {contact_name}")

            if operator_name:
                lines.append(f"🧑‍💼 <b>Оператор:</b> {operator_name}")

            text = "\n".join(lines)

            buttons = [
                [InlineKeyboardButton("📞 Перезвонить", callback_data=f"callback:{caller_phone}")]
            ]

            if not contact_id:
                buttons.append([
                    InlineKeyboardButton("➕ Создать контакт", callback_data=f"create_contact:{caller_phone}")
                ])

            buttons.append([
                InlineKeyboardButton("✅ Обработано", callback_data=f"mark_handled:call_missed:{caller_phone}")
            ])

            reply_markup = InlineKeyboardMarkup(buttons)

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send call_missed notification: {e}", exc_info=True)

    @staticmethod
    async def notify_new_lead(
        session: AsyncSession,
        company_id: UUID,
        lead_id: UUID,
        lead_title: str,
        source: Optional[str] = None,
        contact_name: Optional[str] = None,
        estimated_value: Optional[float] = None,
    ):
        """Send notification for new lead created."""
        config = await _get_config(session, company_id)
        if not config or not config.is_event_enabled("new_lead"):
            return

        bot = _get_bot()
        if not bot:
            return

        try:
            lines = [
                "🆕 <b>Новый лид</b>",
                "",
                f"📝 <b>Название:</b> {lead_title}",
            ]

            if contact_name:
                lines.append(f"👤 <b>Контакт:</b> {contact_name}")

            if source:
                lines.append(f"📡 <b>Источник:</b> {source}")

            if estimated_value:
                lines.append(f"💰 <b>Сумма:</b> {estimated_value:,.0f}")

            text = "\n".join(lines)

            buttons = [
                [InlineKeyboardButton("👤 Назначить", callback_data=f"assign_lead:{lead_id}")],
                [InlineKeyboardButton("✅ Обработано", callback_data=f"mark_handled:new_lead:{lead_id}")]
            ]

            reply_markup = InlineKeyboardMarkup(buttons)

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send new_lead notification: {e}", exc_info=True)

    @staticmethod
    async def notify_deal_stage_change(
        session: AsyncSession,
        company_id: UUID,
        deal_id: UUID,
        deal_title: str,
        old_stage: str,
        new_stage: str,
        amount: Optional[float] = None,
        assigned_to_name: Optional[str] = None,
    ):
        """Send notification for deal stage change."""
        config = await _get_config(session, company_id)
        if not config or not config.is_event_enabled("deal_stage_change"):
            return

        bot = _get_bot()
        if not bot:
            return

        try:
            stage_icons = {
                "prospecting": "🔍",
                "qualification": "📋",
                "proposal": "📄",
                "negotiation": "🤝",
                "closed_won": "🎉",
                "closed_lost": "😞",
            }

            icon = stage_icons.get(new_stage, "📊")
            stage_names = {
                "prospecting": "Поиск",
                "qualification": "Квалификация",
                "proposal": "Предложение",
                "negotiation": "Переговоры",
                "closed_won": "Выиграна",
                "closed_lost": "Проиграна",
            }

            old_name = stage_names.get(old_stage, old_stage)
            new_name = stage_names.get(new_stage, new_stage)

            lines = [
                f"{icon} <b>Смена этапа сделки</b>",
                "",
                f"📝 <b>Сделка:</b> {deal_title}",
                f"🔄 <b>Этап:</b> {old_name} → {new_name}",
            ]

            if amount:
                lines.append(f"💰 <b>Сумма:</b> {amount:,.0f}")

            if assigned_to_name:
                lines.append(f"🧑‍💼 <b>Ответственный:</b> {assigned_to_name}")

            text = "\n".join(lines)

            buttons = [
                [InlineKeyboardButton("✅ Обработано", callback_data=f"mark_handled:deal_stage:{deal_id}")]
            ]

            reply_markup = InlineKeyboardMarkup(buttons)

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send deal_stage_change notification: {e}", exc_info=True)

    @staticmethod
    async def send_test_message(chat_id: str) -> bool:
        """Send a test message to verify bot configuration."""
        bot = _get_bot()
        if not bot:
            return False

        try:
            await bot.send_message(
                chat_id=chat_id,
                text="✅ <b>S1P CRM</b> подключен!\n\nТелеграм-уведомления настроены и работают.",
                parse_mode=ParseMode.HTML
            )
            return True
        except Exception as e:
            logger.error(f"Test message failed: {e}", exc_info=True)
            return False


def _format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    secs = seconds % 60
    if secs:
        return f"{minutes} мин {secs} сек"
    return f"{minutes} мин"
