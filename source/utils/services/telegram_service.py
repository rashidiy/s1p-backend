"""
Telegram notification service — fire-and-forget message sending to company chats.

Uses aiogram Bot instance to send rich Markdown messages with inline keyboards.
All sends are fire-and-forget: errors are logged, never raised.
"""

import logging
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

logger = logging.getLogger(__name__)

# Shared bot instance — initialized once, reused across requests
_bot: Optional[Bot] = None


def get_bot() -> Optional[Bot]:
    """Get or create the shared Bot instance. Returns None if token is not configured."""
    global _bot
    if not TelegramBotConfig.ENABLED:
        return None
    if _bot is None:
        _bot = Bot(token=TelegramBotConfig.BOT_TOKEN)
    return _bot


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r'_*[]()~`>#+-=|{}.!'
    result = []
    for ch in text:
        if ch in special:
            result.append('\\')
        result.append(ch)
    return ''.join(result)


def _crm_url(path: str) -> str:
    """Build CRM frontend URL."""
    base = AppConfig.BASE_URL.rstrip('/')
    return f"{base}/{path.lstrip('/')}"


class TelegramService:
    """
    Sends Telegram notifications to company chats.

    All methods:
    - Check TelegramConfig for the company (enabled + chat_id present)
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
    async def send_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """
        Send a completed call notification to the company's Telegram chat.

        Rich message with caller info, matched contact, duration, direction,
        operator name. Inline keyboard: [Assign Lead] [Mark Handled] [Open in CRM]
        """
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_completed"):
                return

            # Gather data
            contact_name = await TelegramService._lookup_contact_name(
                call_event.phone_1, company_id, session
            )
            operator_name = await TelegramService._get_operator_name(
                call_event.operator_id, session
            )

            direction_label = (call_event.direction.value if call_event.direction else "unknown").capitalize()
            duration = call_event.duration_sec
            minutes = duration // 60
            seconds = duration % 60
            duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

            # Build message
            caller_display = _escape_md(contact_name or call_event.phone_1 or "Unknown")
            lines = [
                f"*{_escape_md(direction_label)} Call Completed*",
                "",
                f"Caller: {caller_display}",
                f"Phone: {_escape_md(call_event.phone_1 or 'N/A')}",
                f"Duration: {_escape_md(duration_str)}",
            ]
            if operator_name:
                lines.append(f"Operator: {_escape_md(operator_name)}")
            if contact_name:
                lines.append(f"Contact: {_escape_md(contact_name)}")

            text = "\n".join(lines)

            # Inline keyboard
            call_id = call_event.id
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Assign Lead",
                        callback_data=f"assign_lead:{call_id}",
                    ),
                    InlineKeyboardButton(
                        text="Mark Handled",
                        callback_data=f"mark_handled:{call_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Open in CRM",
                        url=_crm_url(f"/calls/{call_id}"),
                    ),
                ],
            ])

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send call notification for company %s", company_id
            )

    @staticmethod
    async def send_missed_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """
        Send an urgent missed call notification with [Callback] button.
        """
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("call_missed"):
                return

            contact_name = await TelegramService._lookup_contact_name(
                call_event.phone_1, company_id, session
            )

            caller_display = _escape_md(contact_name or call_event.phone_1 or "Unknown")
            phone_display = _escape_md(call_event.phone_1 or "N/A")

            lines = [
                "*MISSED CALL*",
                "",
                f"From: {caller_display}",
                f"Phone: {phone_display}",
            ]
            if contact_name:
                lines.append(f"Contact: {_escape_md(contact_name)}")

            text = "\n".join(lines)

            call_id = call_event.id
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Callback",
                        callback_data=f"callback:{call_id}",
                    ),
                    InlineKeyboardButton(
                        text="Open in CRM",
                        url=_crm_url(f"/calls/{call_id}"),
                    ),
                ],
            ])

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send missed call notification for company %s", company_id
            )

    @staticmethod
    async def send_lead_notification(
        company_id: UUID,
        lead,
        session: AsyncSession,
    ) -> None:
        """
        Send a new lead notification with [Open Lead] button.
        """
        try:
            bot = get_bot()
            if not bot:
                return

            config = await TelegramService._get_config(company_id, session)
            if not config or not config.is_event_enabled("new_lead"):
                return

            title = _escape_md(lead.title or "Untitled Lead")
            source = _escape_md(lead.source or "N/A")

            lines = [
                "*New Lead Created*",
                "",
                f"Title: {title}",
                f"Source: {source}",
            ]

            if lead.estimated_value:
                value_str = _escape_md(f"{lead.estimated_value} {lead.currency or 'USD'}")
                lines.append(f"Value: {value_str}")

            text = "\n".join(lines)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Open Lead",
                        url=_crm_url(f"/leads/{lead.id}"),
                    ),
                ],
            ])

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send lead notification for company %s", company_id
            )

    # --- Legacy-compatible methods (individual-field signatures) ---

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

            direction_label = direction.capitalize()
            minutes = duration_sec // 60
            seconds = duration_sec % 60
            duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

            caller_display = _escape_md(contact_name or caller_phone or "Unknown")
            lines = [
                f"*{_escape_md(direction_label)} Call Completed*",
                "",
                f"Caller: {caller_display}",
                f"Phone: {_escape_md(caller_phone or 'N/A')}",
                f"Duration: {_escape_md(duration_str)}",
            ]
            if operator_name:
                lines.append(f"Operator: {_escape_md(operator_name)}")
            if contact_name:
                lines.append(f"Contact: {_escape_md(contact_name)}")

            text = "\n".join(lines)

            buttons = []
            if contact_id:
                buttons.append([InlineKeyboardButton(
                    text="Open Contact",
                    url=_crm_url(f"/contacts/{contact_id}"),
                )])

            buttons.append([InlineKeyboardButton(
                text="Mark Handled",
                callback_data=f"mark_handled:call_completed:{caller_phone[:40]}",
            )])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send call_completed notification for company %s", company_id
            )

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

            caller_display = _escape_md(contact_name or caller_phone or "Unknown")
            lines = [
                "*MISSED CALL*",
                "",
                f"From: {caller_display}",
                f"Phone: {_escape_md(caller_phone or 'N/A')}",
            ]
            if operator_name:
                lines.append(f"Operator: {_escape_md(operator_name)}")

            text = "\n".join(lines)

            buttons = [
                [InlineKeyboardButton(
                    text="Callback",
                    callback_data=f"callback:{caller_phone[:40]}",
                )],
                [InlineKeyboardButton(
                    text="Mark Handled",
                    callback_data=f"mark_handled:call_missed:{caller_phone[:40]}",
                )],
            ]

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send call_missed notification for company %s", company_id
            )

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

            title = _escape_md(lead_title or "Untitled Lead")
            lines = [
                "*New Lead Created*",
                "",
                f"Title: {title}",
            ]
            if contact_name:
                lines.append(f"Contact: {_escape_md(contact_name)}")
            if source:
                lines.append(f"Source: {_escape_md(source)}")
            if estimated_value:
                lines.append(f"Value: {_escape_md(f'{estimated_value:,.0f}')}")

            text = "\n".join(lines)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Open Lead",
                    url=_crm_url(f"/leads/{lead_id}"),
                )],
            ])

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send new_lead notification for company %s", company_id
            )

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

            stage_names = {
                "prospecting": "Prospecting",
                "qualification": "Qualification",
                "proposal": "Proposal",
                "negotiation": "Negotiation",
                "closed_won": "Closed Won",
                "closed_lost": "Closed Lost",
            }

            old_name = stage_names.get(old_stage, old_stage)
            new_name = stage_names.get(new_stage, new_stage)

            lines = [
                "*Deal Stage Changed*",
                "",
                f"Deal: {_escape_md(deal_title)}",
                f"Stage: {_escape_md(old_name)} → {_escape_md(new_name)}",
            ]
            if amount:
                lines.append(f"Amount: {_escape_md(f'{amount:,.0f}')}")
            if assigned_to_name:
                lines.append(f"Assigned to: {_escape_md(assigned_to_name)}")

            text = "\n".join(lines)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="Open Deal",
                    url=_crm_url(f"/deals/{deal_id}"),
                )],
                [InlineKeyboardButton(
                    text="Mark Handled",
                    callback_data=f"mark_handled:deal_stage:{str(deal_id)[:36]}",
                )],
            ])

            await bot.send_message(
                chat_id=config.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        except Exception:
            logger.exception(
                "Failed to send deal_stage_change notification for company %s", company_id
            )

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
