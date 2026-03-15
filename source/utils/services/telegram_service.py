"""
Telegram notification service V2 — topic-routed, i18n, fire-and-forget.

Uses aiogram Bot to send MarkdownV2 messages with inline keyboards.
All sends are fire-and-forget: errors are logged, never raised.

V2 additions:
- Topic routing via message_thread_id (calls/missed/leads/deals/general)
- i18n: message templates in ru/en/uz based on company's language setting
- Shortened callback prefixes to fit 64-byte Telegram limit
- Backward compatible: no topics = send to main chat
"""

import logging
import os
from typing import Optional
from uuid import UUID

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import TelegramConfig as TelegramBotConfig, AppConfig
from db.models.telegram_config import TelegramBotConfig as TelegramConfig
from db.models.contact import Contact
from db.models.user import User
from utils.services.telegram_constants import BUTTON_LABELS, get_locale
from utils.services import telegram_i18n as i18n

logger = logging.getLogger(__name__)

# Shared bot instance — initialized once, reused across requests
_bot: Optional[Bot] = None

# Smart grouping TTL (seconds) — edit existing message instead of sending new
GROUPING_WINDOW = 30 * 60  # 30 minutes


def get_bot() -> Optional[Bot]:
    """Get or create the shared Bot instance. Returns None if token is not configured."""
    global _bot
    if not TelegramBotConfig.ENABLED:
        return None
    if _bot is None:
        _bot = Bot(token=TelegramBotConfig.BOT_TOKEN)
    return _bot


def _crm_url(path: str) -> str:
    """Build CRM frontend URL."""
    base = AppConfig.FRONTEND_URL.rstrip('/')
    return f"{base}/{path.lstrip('/')}"


def _buttons(locale: str) -> dict:
    """Get button labels for the given locale."""
    return BUTTON_LABELS.get(locale, BUTTON_LABELS["ru"])


class TelegramService:
    """
    Sends Telegram notifications to company chats.

    All methods:
    - Check TelegramConfig for the company (enabled + chat_id present)
    - Route to the correct forum topic if topics are configured
    - Use i18n templates based on company's language setting
    - Skip silently if not configured
    - Log errors, never raise
    """

    @staticmethod
    async def _get_config(company_id: UUID, session: AsyncSession) -> Optional[TelegramConfig]:
        """Load TelegramConfig for company. Returns None if not connected/enabled."""
        config = await TelegramConfig.get(
            session=session,
            company_id=company_id,
        )
        if not config or not config.enabled:
            return None
        return config

    @staticmethod
    async def _lookup_contact_name(phone: str, company_id: UUID, session: AsyncSession) -> Optional[str]:
        """Try to find a contact name by phone number within the company."""
        if not phone:
            return None
        result = await session.execute(
            select(Contact.first_name, Contact.last_name, Contact.company_name)
            .where(
                Contact.company_id == company_id,
                Contact.phone == phone,
                Contact.deleted_at.is_(None),
            )
            .limit(1)
        )
        row = result.first()
        if not row:
            return None
        first, last, company = row
        if first and last:
            return f"{first} {last}"
        return first or last or company or None

    @staticmethod
    async def _get_operator_name(operator_id: Optional[UUID], session: AsyncSession) -> Optional[str]:
        """Get operator display name by user ID."""
        if not operator_id:
            return None
        user = await User.get(session=session, id=operator_id)
        if not user:
            return None
        return user.full_name

    @staticmethod
    async def _get_redis():
        """Get Redis client for smart grouping. Returns None if unavailable."""
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            return aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        except Exception:
            return None

    @staticmethod
    async def _check_grouping(
        bot: Bot,
        config: TelegramConfig,
        phone: str,
        event_type: str,
        text: str,
    ) -> bool:
        """
        Smart grouping: if a recent message exists for the same phone+event,
        edit it with an incremented count instead of sending a new message.

        Returns True if grouped (message edited), False if should send new.
        Only applies to call notifications.
        """
        if event_type not in ("call_completed", "call_missed"):
            return False
        if not phone:
            return False

        redis = await TelegramService._get_redis()
        if not redis:
            return False

        key = f"tg:msg:{config.company_id}:{phone}:{event_type}"
        try:
            existing = await redis.get(key)
            if not existing:
                return False

            # Parse "message_id:count"
            parts = existing.split(":")
            if len(parts) != 2:
                return False

            message_id, count = int(parts[0]), int(parts[1])
            new_count = count + 1

            # Edit existing message with count suffix
            chat_id = config.effective_chat_id
            lang = config.language or "ru"
            suffix = i18n.grouped_suffix(new_count, lang)
            new_text = f"{text}\n\n{suffix}"

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                # Update count in Redis
                await redis.setex(key, GROUPING_WINDOW, f"{message_id}:{new_count}")
                return True
            except Exception:
                # Edit failed (message too old, deleted, etc.) — send new
                return False
        except Exception:
            return False
        finally:
            await redis.aclose()

    @staticmethod
    async def _store_grouping(
        config: TelegramConfig,
        phone: str,
        event_type: str,
        message_id: int,
    ) -> None:
        """Store message_id for smart grouping (30min window)."""
        if event_type not in ("call_completed", "call_missed"):
            return
        if not phone:
            return

        redis = await TelegramService._get_redis()
        if not redis:
            return

        key = f"tg:msg:{config.company_id}:{phone}:{event_type}"
        try:
            await redis.setex(key, GROUPING_WINDOW, f"{message_id}:1")
        except Exception:
            pass
        finally:
            await redis.aclose()

    @staticmethod
    async def _send(
        bot: Bot,
        config: TelegramConfig,
        text: str,
        event_type: str,
        keyboard: InlineKeyboardMarkup | None = None,
        phone: str | None = None,
    ) -> Optional[int]:
        """
        Send a message to the right chat/topic.
        Supports smart grouping for call notifications.

        Returns message_id on success, None on failure.
        """
        chat_id = config.effective_chat_id
        if not chat_id:
            return None

        # Smart grouping: try to edit existing message
        if phone and await TelegramService._check_grouping(bot, config, phone, event_type, text):
            return None  # Grouped into existing message

        thread_id = config.get_topic_thread_id(event_type)

        kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": ParseMode.MARKDOWN_V2,
        }
        if keyboard:
            kwargs["reply_markup"] = keyboard
        if thread_id:
            kwargs["message_thread_id"] = thread_id

        result = await bot.send_message(**kwargs)

        # Store for future grouping
        if phone:
            await TelegramService._store_grouping(config, phone, event_type, result.message_id)

        return result.message_id

    # ── Public API: object-based signatures ──────────────────────

    @staticmethod
    async def send_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """Send a completed call notification with topic routing + i18n."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_completed"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            contact_name = await TelegramService._lookup_contact_name(
                call_event.phone_1, company_id, session
            )
            operator_name = await TelegramService._get_operator_name(
                call_event.operator_id, session
            )

            direction = (call_event.direction.value if call_event.direction else "unknown")

            text = i18n.call_completed_message(
                direction=direction,
                caller_display=contact_name or call_event.phone_1 or "Unknown",
                phone=call_event.phone_1 or "N/A",
                duration_sec=call_event.duration_sec or 0,
                operator_name=operator_name,
                contact_name=contact_name,
                lang=lang,
            )

            call_id = call_event.id
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text=btn["assign_lead"], callback_data=f"al:{call_id}"),
                    InlineKeyboardButton(text=btn["mark_handled"], callback_data=f"mh:{call_id}"),
                ],
                [
                    InlineKeyboardButton(text=btn["open_crm"], url=_crm_url(f"/calls/{call_id}")),
                ],
            ])

            await TelegramService._send(bot, config, text, "call_completed", keyboard, phone=call_event.phone_1)
        except Exception:
            logger.exception("Failed to send call notification for company %s", company_id)

    @staticmethod
    async def send_missed_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """Send a missed call notification with topic routing + i18n."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_missed"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            contact_name = await TelegramService._lookup_contact_name(
                call_event.phone_1, company_id, session
            )

            text = i18n.missed_call_message(
                caller_display=contact_name or call_event.phone_1 or "Unknown",
                phone=call_event.phone_1 or "N/A",
                contact_name=contact_name,
                lang=lang,
            )

            call_id = call_event.id
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text=btn["callback"], callback_data=f"cb:{call_id}"),
                    InlineKeyboardButton(text=btn["open_crm"], url=_crm_url(f"/calls/{call_id}")),
                ],
            ])

            await TelegramService._send(bot, config, text, "call_missed", keyboard, phone=call_event.phone_1)
        except Exception:
            logger.exception("Failed to send missed call notification for company %s", company_id)

    @staticmethod
    async def send_lead_notification(
        company_id: UUID,
        lead,
        session: AsyncSession,
    ) -> None:
        """Send a new lead notification with topic routing + i18n."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("new_lead"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            text = i18n.new_lead_message(
                lead_title=lead.title or "Untitled",
                source=lead.source,
                estimated_value=lead.estimated_value,
                currency=lead.currency or "USD",
                lang=lang,
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn["open_lead"], url=_crm_url(f"/leads/{lead.id}"))],
            ])

            await TelegramService._send(bot, config, text, "new_lead", keyboard)
        except Exception:
            logger.exception("Failed to send lead notification for company %s", company_id)

    # ── Legacy-compatible methods (individual-field signatures) ──

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
        """Send notification for completed call (individual-field signature)."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_completed"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            text = i18n.call_completed_message(
                direction=direction,
                caller_display=contact_name or caller_phone or "Unknown",
                phone=caller_phone or "N/A",
                duration_sec=duration_sec,
                operator_name=operator_name,
                contact_name=contact_name,
                recording_url=record_url,
                lang=lang,
            )

            buttons = []
            if contact_id:
                buttons.append([InlineKeyboardButton(
                    text=btn["open_crm"],
                    url=_crm_url(f"/contacts/{contact_id}"),
                )])
            buttons.append([InlineKeyboardButton(
                text=btn["mark_handled"],
                callback_data=f"mh:{caller_phone[:50]}",
            )])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await TelegramService._send(bot, config, text, "call_completed", keyboard, phone=caller_phone)
        except Exception:
            logger.exception("Failed to send call_completed notification for company %s", company_id)

    @staticmethod
    async def notify_call_missed(
        session: AsyncSession,
        company_id: UUID,
        caller_phone: str,
        operator_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_id: Optional[UUID] = None,
    ):
        """Send notification for missed call (individual-field signature)."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_missed"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            text = i18n.missed_call_message(
                caller_display=contact_name or caller_phone or "Unknown",
                phone=caller_phone or "N/A",
                contact_name=contact_name,
                lang=lang,
            )

            buttons = [
                [InlineKeyboardButton(text=btn["callback"], callback_data=f"cb:{caller_phone[:50]}")],
                [InlineKeyboardButton(text=btn["mark_handled"], callback_data=f"mh:{caller_phone[:50]}")],
            ]

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await TelegramService._send(bot, config, text, "call_missed", keyboard, phone=caller_phone)
        except Exception:
            logger.exception("Failed to send call_missed notification for company %s", company_id)

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
        """Send notification for new lead (individual-field signature)."""
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("new_lead"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            text = i18n.new_lead_message(
                lead_title=lead_title or "Untitled",
                source=source,
                estimated_value=estimated_value,
                contact_name=contact_name,
                lang=lang,
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn["open_lead"], url=_crm_url(f"/leads/{lead_id}"))],
            ])

            await TelegramService._send(bot, config, text, "new_lead", keyboard)
        except Exception:
            logger.exception("Failed to send new_lead notification for company %s", company_id)

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
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("deal_stage_change"):
                return

            lang = config.language or "ru"
            locale = get_locale(lang)
            btn = _buttons(locale)

            text = i18n.deal_stage_message(
                deal_title=deal_title,
                old_stage=old_stage,
                new_stage=new_stage,
                amount=amount,
                assigned_to_name=assigned_to_name,
                lang=lang,
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn["open_deal"], url=_crm_url(f"/deals/{deal_id}"))],
                [InlineKeyboardButton(text=btn["mark_handled"], callback_data=f"mh:{str(deal_id)[:36]}")],
            ])

            await TelegramService._send(bot, config, text, "deal_stage_change", keyboard)
        except Exception:
            logger.exception("Failed to send deal_stage_change notification for company %s", company_id)

    @staticmethod
    async def send_test_message(chat_id: str) -> bool:
        """Send a test message to verify bot configuration."""
        bot = get_bot()
        if not bot:
            return False

        try:
            await bot.send_message(
                chat_id=chat_id,
                text="S1P CRM connected\\!\n\nTelegram notifications are configured and working\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return True
        except Exception:
            logger.exception("Test message failed for chat_id %s", chat_id)
            return False

    # ── Forum topic creation (via Bot API) ───────────────────────

    @staticmethod
    async def create_forum_topics(chat_id: str | int) -> dict[str, int]:
        """
        Create forum topics in an existing supergroup using the Bot API.

        Returns: {"calls": thread_id, "missed": thread_id, ...}
        Used by manual setup flow when Pyrogram is not available.
        """
        from utils.services.telegram_constants import TOPIC_NAMES, TOPIC_EMOJI

        bot = get_bot()
        if not bot:
            raise RuntimeError("Bot not available")

        topic_ids = {"general": 1}  # General is always thread_id=1

        for topic_key in ["calls", "missed", "leads", "deals"]:
            emoji = TOPIC_EMOJI[topic_key]
            name = f"{emoji} {TOPIC_NAMES['ru'][topic_key]}"

            result = await bot.create_forum_topic(
                chat_id=chat_id,
                name=name,
            )
            topic_ids[topic_key] = result.message_thread_id

        return topic_ids
