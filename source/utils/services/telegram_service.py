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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReactionTypeEmoji, BufferedInputFile
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


def _crm_url(path: str, subdomain: str | None = None) -> str | None:
    """Build CRM frontend URL with company subdomain.

    Example: subdomain='logistic' → https://logistic.s1p.uz/calls/123
    Returns None if URL wouldn't be valid for Telegram (non-HTTPS).
    """
    base = AppConfig.FRONTEND_URL.rstrip('/')
    if subdomain and base.startswith("https://"):
        # Insert subdomain: https://s1p.uz → https://logistic.s1p.uz
        base = base.replace("https://", f"https://{subdomain}.", 1)
    url = f"{base}/{path.lstrip('/')}"
    if not url.startswith("https://"):
        return None
    return url


def _url_button(text: str, path: str, subdomain: str | None = None) -> InlineKeyboardButton | None:
    """Create a URL button, or None if the URL isn't valid for Telegram."""
    url = _crm_url(path, subdomain)
    if not url:
        return None
    return InlineKeyboardButton(text=text, url=url)


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
    async def _get_subdomain(company_id: UUID, session: AsyncSession) -> str | None:
        """Get company subdomain for CRM URL buttons."""
        from db.models.company import Company
        result = await session.execute(
            select(Company.subdomain).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

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

    # ── Recording audio helper ──────────────────────────────────

    _thumbnail_data: bytes | None = None

    @classmethod
    def _get_thumbnail_data(cls) -> bytes:
        """Load S1P audio thumbnail bytes (cached after first call)."""
        if cls._thumbnail_data is None:
            from pathlib import Path
            logo_path = Path(__file__).resolve().parent.parent.parent / "static" / "s1p_audio_thumb.jpg"
            cls._thumbnail_data = logo_path.read_bytes() if logo_path.exists() else b""
        return cls._thumbnail_data

    @classmethod
    def _embed_cover_art(cls, audio_data: bytes, title: str, performer: str) -> bytes:
        """Embed album art + metadata into MP3 via ID3 tags for full-res display."""
        cover = cls._get_thumbnail_data()
        if not cover:
            return audio_data
        try:
            import io
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3, APIC, TIT2, TPE1

            buf = io.BytesIO(audio_data)
            audio = MP3(buf)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(APIC(mime="image/jpeg", type=3, desc="Cover", data=cover))
            audio.tags.add(TIT2(encoding=3, text=[title]))
            audio.tags.add(TPE1(encoding=3, text=[performer]))
            buf.seek(0)
            audio.save(buf)
            return buf.getvalue()
        except Exception:
            logger.debug("Failed to embed cover art into MP3")
            return audio_data

    @staticmethod
    async def _download_recording(recording_url: str) -> bytes | None:
        """Download a call recording via residential proxy. Returns audio bytes or None."""
        try:
            import httpx
            proxy_url = os.getenv("RESIDENTIAL_PROXY_URL") or None
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0, proxy=proxy_url,
            ) as client:
                resp = await client.get(recording_url)
                if resp.status_code != 200:
                    logger.warning("Recording download failed: HTTP %s for %s", resp.status_code, recording_url)
                    return None
                if len(resp.content) < 100:
                    logger.warning("Recording too small (%d bytes): %s", len(resp.content), recording_url)
                    return None
                return resp.content
        except Exception:
            logger.warning("Recording download error for %s", recording_url, exc_info=True)
            return None

    @staticmethod
    async def send_recording_audio(
        bot: Bot,
        chat_id: str | int,
        recording_url: str,
        phone: str | None = None,
        caption: str | None = None,
        thread_id: int | None = None,
        keyboard: InlineKeyboardMarkup | None = None,
        parse_mode: str | None = None,
        filename: str = "recording.mp3",
        title: str | None = None,
        performer: str | None = None,
    ) -> bool:
        """
        Download a call recording and send it as audio with optional caption + buttons.
        Falls back silently on failure (caller should handle fallback to text message).
        """
        try:
            audio_data = await TelegramService._download_recording(recording_url)
            if not audio_data:
                return False

            filename = f"{phone}.mp3" if phone else "recording.mp3"
            actual_title = title or (phone if phone else filename)
            actual_performer = performer or "s1p.uz"

            # Embed full-res cover art into MP3 ID3 tags (for lock screen / now playing)
            audio_data = TelegramService._embed_cover_art(audio_data, actual_title, actual_performer)

            kwargs = {
                "chat_id": chat_id,
                "audio": BufferedInputFile(audio_data, filename=filename),
                "title": actual_title,
                "performer": actual_performer,
            }
            # Also send 320px thumbnail for chat bubble preview
            thumb_data = TelegramService._get_thumbnail_data()
            if thumb_data:
                kwargs["thumbnail"] = BufferedInputFile(thumb_data, filename="thumbnail.jpg")
            if caption:
                kwargs["caption"] = caption[:1024]  # Telegram caption limit
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            if keyboard:
                kwargs["reply_markup"] = keyboard

            await bot.send_audio(**kwargs)
            return True
        except Exception:
            logger.warning("Failed to send recording audio to chat %s", chat_id, exc_info=True)
            return False

    # ── Public API: object-based signatures ──────────────────────

    @staticmethod
    async def send_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """Send a completed (answered) call notification — clean 2-line format."""
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

            direction = (call_event.direction.value if call_event.direction else "unknown")

            # External party phone: phone_2 for outbound, phone_1 for inbound
            if direction == "outbound":
                display_phone = call_event.phone_2 or call_event.phone_1 or ""
            else:
                display_phone = call_event.phone_1 or ""

            contact_name = await TelegramService._lookup_contact_name(
                display_phone, company_id, session
            )
            operator_name = await TelegramService._get_operator_name(
                call_event.operator_id, session
            )

            duration_sec = call_event.billing_sec or 0
            if not duration_sec and call_event.call_end_timestamp and call_event.call_answer_timestamp:
                duration_sec = max(0, call_event.call_end_timestamp - call_event.call_answer_timestamp)

            call_id = call_event.id

            msg_args = dict(
                direction=direction,
                caller_display=contact_name or display_phone or "Unknown",
                phone=display_phone or "N/A",
                duration_sec=duration_sec,
                operator_name=operator_name,
                contact_name=contact_name,
                call_id=call_id,
                lang=lang,
            )

            company_id_str = str(company_id)
            subdomain = await TelegramService._get_subdomain(company_id, session)
            from utils.services.startapp_service import build_miniapp_url

            # Single row: [📱 Подробнее] [📋 CRM]
            nav_row = [
                InlineKeyboardButton(
                    text=btn["details"],
                    url=build_miniapp_url("call_detail", str(call_id), company_id_str),
                ),
            ]
            crm_btn = _url_button(btn["open_crm"], f"/calls/{call_id}", subdomain)
            if crm_btn:
                nav_row.append(crm_btn)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_row])

            recording_url = getattr(call_event, 'record_url', None)
            sent_as_audio = False

            # Try to send as audio with HTML caption (supports clickable #hashtags)
            if recording_url and config.send_recordings:
                thread_id = config.get_topic_thread_id("call_completed")
                chat_id = config.effective_chat_id
                if chat_id:
                    html_text = i18n.call_completed_message(**msg_args, html=True)
                    sent_as_audio = await TelegramService.send_recording_audio(
                        bot, chat_id, recording_url,
                        phone=display_phone,
                        caption=html_text, thread_id=thread_id,
                        keyboard=keyboard, parse_mode=ParseMode.HTML,
                    )

            # Fallback to text message (MarkdownV2)
            text_md = i18n.call_completed_message(**msg_args)
            if not sent_as_audio:
                await TelegramService._send(
                    bot, config, text_md, "call_completed", keyboard, phone=display_phone,
                )

            # DM to operator
            await TelegramService._send_dm_notifications(
                config, "call_completed", text_md, session,
                operator_id=call_event.operator_id,
                call_id=call_id,
                contact_id=call_event.contact_id,
            )
        except Exception:
            logger.exception("Failed to send call notification for company %s", company_id)

    @staticmethod
    async def send_missed_call_notification(
        company_id: UUID,
        call_event,
        session: AsyncSession,
    ) -> None:
        """Send missed/unanswered call notification — direction-aware."""
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

            direction = (call_event.direction.value if call_event.direction else "inbound")
            is_outbound = direction == "outbound"

            # External party phone
            if is_outbound:
                display_phone = call_event.phone_2 or call_event.phone_1 or ""
            else:
                display_phone = call_event.phone_1 or ""

            contact_name = await TelegramService._lookup_contact_name(
                display_phone, company_id, session
            )
            operator_name = await TelegramService._get_operator_name(
                call_event.operator_id, session
            )

            call_id = call_event.id
            company_id_str = str(company_id)
            subdomain = await TelegramService._get_subdomain(company_id, session)
            from utils.services.startapp_service import build_miniapp_url

            if is_outbound:
                # Outbound unanswered: 📵 Олег → Contact / Не дозвонились
                text = i18n.outbound_unanswered_message(
                    operator_name=operator_name,
                    caller_display=contact_name or display_phone or "Unknown",
                    phone=display_phone or "N/A",
                    contact_name=contact_name,
                    call_id=call_id,
                    lang=lang,
                )
                # [📱 Повторить] [📋 CRM]
                nav_row = [
                    InlineKeyboardButton(
                        text=btn["retry"],
                        url=build_miniapp_url("call_detail", str(call_id), company_id_str),
                    ),
                ]
            else:
                # Inbound missed: 🔴 Пропущен от Contact
                text = i18n.missed_call_message(
                    caller_display=contact_name or display_phone or "Unknown",
                    phone=display_phone or "N/A",
                    contact_name=contact_name,
                    call_id=call_id,
                    lang=lang,
                )
                # [📱 Перезвонить] [📋 CRM]
                nav_row = [
                    InlineKeyboardButton(
                        text=btn["callback_mini"],
                        url=build_miniapp_url("call_detail", str(call_id), company_id_str),
                    ),
                ]

            crm_btn = _url_button(btn["open_crm"], f"/calls/{call_id}", subdomain)
            if crm_btn:
                nav_row.append(crm_btn)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_row])

            msg_id = await TelegramService._send(
                bot, config, text, "call_missed", keyboard, phone=display_phone,
            )

            # Save telegram message_id for escalation replies (inbound only)
            if not is_outbound and msg_id and call_event.id:
                from db.models.call_event import CallEvent
                await session.execute(
                    CallEvent.__table__.update()
                    .where(CallEvent.id == call_event.id)
                    .where(CallEvent.company_id == company_id)
                    .values(telegram_message_id=msg_id)
                )
                await session.commit()

            # DMs: inbound missed → ALL users, outbound unanswered → operator only
            await TelegramService._send_dm_notifications(
                config, "call_missed", text, session,
                operator_id=call_event.operator_id if is_outbound else None,
                call_id=call_id,
                contact_id=call_event.contact_id,
            )
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

            from utils.services.startapp_service import build_miniapp_url
            company_id_str = str(company_id)
            subdomain = await TelegramService._get_subdomain(company_id, session)

            nav_row = [
                InlineKeyboardButton(
                    text=btn["open_lead"],
                    url=build_miniapp_url("lead_detail", str(lead.id), company_id_str),
                ),
            ]
            crm_btn = _url_button(btn["open_crm"], f"/leads/{lead.id}", subdomain)
            if crm_btn:
                nav_row.append(crm_btn)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_row])

            await TelegramService._send(bot, config, text, "new_lead", keyboard)

            # DM notifications — scoped to lead assignee
            await TelegramService._send_dm_notifications(
                config, "new_lead", text, session,
                operator_id=lead.assigned_to,
                lead_id=lead.id,
            )
        except Exception:
            logger.exception("Failed to send lead notification for company %s", company_id)

    # Legacy methods removed — all call notifications now use
    # send_call_notification() and send_missed_call_notification()
    # with the call_event object.

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

            lead_btn = _url_button(btn["open_lead"], f"/leads/{lead_id}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[lead_btn]]) if lead_btn else None

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
        assigned_to_id: Optional[UUID] = None,
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

            from utils.services.startapp_service import build_miniapp_url
            company_id_str = str(company_id)
            subdomain = await TelegramService._get_subdomain(company_id, session)

            rows = [
                [InlineKeyboardButton(
                    text=btn["open_deal"],
                    url=build_miniapp_url("deal_detail", str(deal_id), company_id_str),
                )],
                [InlineKeyboardButton(text=btn["mark_handled"], callback_data=f"mh:{str(deal_id)[:36]}")],
            ]
            crm_btn = _url_button(btn["open_crm"], f"/deals/{deal_id}", subdomain)
            if crm_btn:
                rows[0].append(crm_btn)
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

            await TelegramService._send(bot, config, text, "deal_stage_change", keyboard)

            # DM notifications — scoped to deal assignee
            await TelegramService._send_dm_notifications(
                config, "deal_stage_change", text, session,
                operator_id=assigned_to_id,
                deal_id=deal_id,
            )
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
    async def create_forum_topics(chat_id: str | int, lang: str = "ru") -> dict[str, int]:
        """
        Create forum topics in an existing supergroup using the Bot API.

        Returns: {"calls": thread_id, "missed": thread_id, ..., "general": 1}
        Topics use custom emoji icons (circular icon on the left), not text emoji in the name.
        """
        from utils.services.telegram_constants import TOPIC_NAMES, TOPIC_ICON_EMOJI_ID
        import asyncio as _asyncio

        bot = get_bot()
        if not bot:
            raise RuntimeError("Bot not available")

        locale = lang if lang in TOPIC_NAMES else "ru"
        topic_ids = {"general": 1}  # General is always thread_id=1

        for topic_key in ["calls", "leads", "deals"]:
            name = TOPIC_NAMES[locale][topic_key]
            icon_emoji_id = TOPIC_ICON_EMOJI_ID.get(topic_key)

            kwargs = {"chat_id": chat_id, "name": name}
            if icon_emoji_id:
                kwargs["icon_custom_emoji_id"] = icon_emoji_id

            try:
                result = await bot.create_forum_topic(**kwargs)
                topic_ids[topic_key] = result.message_thread_id
            except Exception:
                logger.warning("Failed to create topic %s in chat %s", topic_key, chat_id)

            await _asyncio.sleep(0.3)  # Rate limit safety between topic creation

        # Rename General topic to match language
        general_name = TOPIC_NAMES[locale].get("general")
        if general_name:
            try:
                await bot.edit_general_forum_topic(chat_id=chat_id, name=general_name)
            except Exception:
                logger.debug("Could not rename General topic in chat %s", chat_id)

        # Reopen General topic so all members can send messages
        try:
            await bot.reopen_general_forum_topic(chat_id=chat_id)
        except Exception:
            logger.debug("Could not reopen General topic in chat %s", chat_id)

        # Set group photo
        try:
            from aiogram.types import FSInputFile
            logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "s1p_group_logo.png")
            logo_path = os.path.normpath(logo_path)
            if os.path.exists(logo_path):
                await bot.set_chat_photo(chat_id=chat_id, photo=FSInputFile(logo_path))
        except Exception:
            logger.debug("Could not set group photo for chat %s", chat_id)

        return topic_ids

    # ── Forum topic renaming ────────────────────────────────────

    @staticmethod
    async def rename_forum_topics(chat_id: str | int, topic_ids: dict, lang: str = "ru") -> None:
        """
        Rename forum topics to match the given language.
        Called when the notification language is changed.
        """
        from utils.services.telegram_constants import TOPIC_NAMES

        bot = get_bot()
        if not bot:
            return

        locale = lang if lang in TOPIC_NAMES else "ru"

        for topic_key in ["calls", "leads", "deals"]:
            thread_id = topic_ids.get(topic_key)
            if not thread_id:
                continue

            name = TOPIC_NAMES[locale][topic_key]
            try:
                await bot.edit_forum_topic(
                    chat_id=chat_id,
                    message_thread_id=thread_id,
                    name=name,
                )
            except Exception:
                logger.debug("Failed to rename topic %s in chat %s", topic_key, chat_id)

        # Rename General topic
        general_name = TOPIC_NAMES[locale].get("general")
        if general_name:
            try:
                await bot.edit_general_forum_topic(
                    chat_id=chat_id,
                    name=general_name,
                )
            except Exception:
                logger.debug("Failed to rename General topic in chat %s", chat_id)

    # ── Bot reactions ───────────────────────────────────────────

    @staticmethod
    async def react_to_message(
        chat_id: str | int,
        message_id: int,
        emoji: str = "✅",
    ) -> None:
        """Add a reaction to a message. Fire-and-forget."""
        bot = get_bot()
        if not bot:
            return
        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
        except Exception:
            logger.debug("Failed to react to message %s in chat %s", message_id, chat_id)

    # ── DM notifications ─────────────────────────────────────────

    @staticmethod
    def _is_quiet_hours(prefs: dict) -> bool:
        """Check if current hour (in user's timezone) falls within quiet hours range.

        Uses timezone_offset from prefs if available, otherwise defaults to +5 (Tashkent).
        """
        start = prefs.get("quiet_hours_start")
        end = prefs.get("quiet_hours_end")
        if start is None or end is None:
            return False
        from datetime import datetime as _dt, timezone as _tz
        # Use timezone_offset from DM prefs; default to +5 (Asia/Tashkent) for CIS users
        offset = prefs.get("timezone_offset", 5)
        current_hour = (_dt.now(_tz.utc).hour + offset) % 24
        if start <= end:
            # Simple range, e.g. 9-17
            return start <= current_hour < end
        else:
            # Wrap-around, e.g. 22-07 means quiet from 22:00 to 06:59
            return current_hour >= start or current_hour < end

    @staticmethod
    def _build_dm_keyboard(
        event_type: str,
        call_id=None,
        contact_id=None,
        lead_id=None,
        deal_id=None,
        language: str = "ru",
        company_id: str | None = None,
    ) -> InlineKeyboardMarkup | None:
        """Build inline keyboard for DM notifications using startapp signed deep links."""
        from utils.services.startapp_service import build_miniapp_url

        locale = get_locale(language)
        btn = _buttons(locale)
        cid = company_id or ""

        rows = []

        if event_type in ("call_completed", "call_missed"):
            if cid and call_id:
                row = [InlineKeyboardButton(
                    text=btn["details"],
                    url=build_miniapp_url("call_detail", str(call_id), cid),
                )]
                rows.append(row)

        elif event_type == "new_lead" and lead_id:
            if cid:
                rows.append([InlineKeyboardButton(
                    text=btn["open_lead"],
                    url=build_miniapp_url("lead_detail", str(lead_id), cid),
                )])

        elif event_type == "deal_stage_change" and deal_id:
            if cid:
                rows.append([InlineKeyboardButton(
                    text=btn["open_deal"],
                    url=build_miniapp_url("deal_detail", str(deal_id), cid),
                )])

        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    @staticmethod
    async def _send_dm_notifications(
        config: TelegramConfig,
        event_type: str,
        text: str,
        session: AsyncSession,
        operator_id: Optional[UUID] = None,
        call_id=None,
        contact_id=None,
        lead_id=None,
        deal_id=None,
    ) -> None:
        """
        Send DM notifications to operators who have DM prefs enabled.

        Fire-and-forget, rate limited to 1 DM per event per user.
        Only sends if config.dm_notifications is True.
        Respects quiet hours from user's telegram_dm_prefs.
        """
        if not config.dm_notifications:
            return

        bot = get_bot()
        if not bot:
            return

        # Map event_type to DM pref key
        pref_map = {
            "call_completed": "my_calls",
            "call_missed": "my_calls",
            "new_lead": "my_leads",
            "deal_stage_change": "assigned_to_me",
        }
        pref_key = pref_map.get(event_type)
        if not pref_key:
            return

        # Build inline keyboard for DM
        lang = config.language or "ru"
        keyboard = TelegramService._build_dm_keyboard(
            event_type,
            call_id=call_id,
            contact_id=contact_id,
            lead_id=lead_id,
            deal_id=deal_id,
            language=lang,
            company_id=str(config.company_id),
        )

        try:
            # Find users with DM prefs enabled for this event type
            from sqlalchemy import select as sa_select
            result = await session.execute(
                sa_select(User).where(
                    User.company_id == config.company_id,
                    User.telegram_user_id.isnot(None),
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                )
            )
            users = result.scalars().all()

            for user in users:
                prefs = user.telegram_dm_prefs or {}
                if not prefs.get(pref_key, False):
                    continue

                # If operator_id provided, only DM that specific user (scoped notifications)
                if operator_id and user.id != operator_id:
                    continue

                # Check quiet hours
                if TelegramService._is_quiet_hours(prefs):
                    continue

                try:
                    kwargs = {
                        "chat_id": user.telegram_user_id,
                        "text": text,
                        "parse_mode": ParseMode.MARKDOWN_V2,
                    }
                    if keyboard:
                        kwargs["reply_markup"] = keyboard
                    await bot.send_message(**kwargs)
                except Exception:
                    logger.debug("Failed to send DM to user %s", user.id)

        except Exception:
            logger.debug("DM notification failed for company %s", config.company_id)
