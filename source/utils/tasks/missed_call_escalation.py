"""
Missed call escalation — sends reminders for unresolved missed inbound calls.

Runs as an asyncio background task every 60 seconds.
Checks for calls with needs_callback=true and escalates based on age:
  - 5 min: reply to original missed call message in calls topic
  - 15 min: urgent reply to original message
  - 30 min: critical reply + DM to all managers (fallback: admins)
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CHECK_INTERVAL = int(os.getenv("ESCALATION_CHECK_INTERVAL", "60"))  # seconds

# Escalation thresholds in minutes
TIER1_MINUTES = int(os.getenv("ESCALATION_TIER1_MIN", "5"))
TIER2_MINUTES = int(os.getenv("ESCALATION_TIER2_MIN", "15"))
TIER3_MINUTES = int(os.getenv("ESCALATION_TIER3_MIN", "30"))


async def check_missed_calls():
    """
    Find unresolved missed calls and send escalation notifications.

    Uses Redis to track which escalation tier has been sent per call,
    so we don't spam the same notification repeatedly.
    """
    from sqlalchemy import select, and_
    from db import async_session_factory
    from db.models.call_event import CallEvent
    from db.models.telegram_config import TelegramBotConfig
    from db.models.user import User
    from db.models.enums import RoleEnum
    from utils.services.telegram_service import get_bot
    from utils.services.startapp_service import build_miniapp_url

    bot = get_bot()
    if not bot:
        return

    # Redis for tracking sent escalations
    redis = None
    try:
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis = aioredis.from_url(redis_url)
    except Exception:
        logger.warning("Escalation: Redis unavailable, skipping to avoid duplicates")
        return

    try:
        async with async_session_factory() as session:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=2)

            result = await session.execute(
                select(CallEvent).where(
                    and_(
                        CallEvent.needs_callback.is_(True),
                        CallEvent.direction == 'inbound',
                        CallEvent.created_at >= cutoff,
                    )
                )
            )
            missed_calls = result.scalars().all()

            # Group by (company_id, phone) — send ONE escalation per phone, not per call
            from collections import defaultdict
            phone_groups: dict[tuple, list] = defaultdict(list)
            for call in missed_calls:
                phone = call.phone_1 or "Unknown"
                key = (call.company_id, phone)
                phone_groups[key].append(call)

            from aiogram.enums import ParseMode
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from utils.services import telegram_i18n as i18n

            for (company_id, phone), calls_in_group in phone_groups.items():
                # Use the OLDEST call in the group to determine tier (highest urgency)
                oldest_call = min(calls_in_group, key=lambda c: c.created_at)
                age_minutes = (now - oldest_call.created_at).total_seconds() / 60

                # Determine tier based on oldest call
                tier = 0
                if age_minutes >= TIER3_MINUTES:
                    tier = 3
                elif age_minutes >= TIER2_MINUTES:
                    tier = 2
                elif age_minutes >= TIER1_MINUTES:
                    tier = 1
                else:
                    continue

                # Check if already escalated for this phone (use phone-based key)
                phone_key = f"escalation:{company_id}:phone:{phone}"
                sent_tier = await redis.get(phone_key)
                if sent_tier and int(sent_tier) >= tier:
                    continue

                # Get Telegram config
                tg_config = await session.execute(
                    select(TelegramBotConfig).where(
                        TelegramBotConfig.company_id == company_id,
                        TelegramBotConfig.enabled.is_(True),
                        TelegramBotConfig.deleted_at.is_(None),
                    )
                )
                config = tg_config.scalar_one_or_none()
                if not config:
                    continue

                chat_id = config.effective_chat_id
                if not chat_id:
                    continue

                lang = config.language or "ru"
                thread_id = config.get_topic_thread_id("call_missed")

                # Use the most recent call for reply threading and operator info
                latest_call = max(calls_in_group, key=lambda c: c.created_at)

                operator_name = None
                if latest_call.operator_id:
                    op = await session.get(User, latest_call.operator_id)
                    if op:
                        operator_name = op.full_name

                company_id_str = str(company_id)
                age_str = f"{int(age_minutes)}"

                text = i18n.escalation_message(
                    phone, operator_name, age_str, tier, lang
                )

                # Build Mini App callback button
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="📞 Перезвонить",
                        url=build_miniapp_url("call", phone, company_id_str),
                    )],
                ])

                kwargs = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": ParseMode.MARKDOWN_V2,
                    "reply_markup": keyboard,
                }
                if thread_id:
                    kwargs["message_thread_id"] = thread_id
                # Reply to the most recent missed call message
                if latest_call.telegram_message_id:
                    kwargs["reply_to_message_id"] = latest_call.telegram_message_id
                    kwargs["allow_sending_without_reply"] = True

                try:
                    await bot.send_message(**kwargs)
                    # Mark phone-level key to prevent duplicate escalations
                    await redis.set(phone_key, str(tier), ex=10800)
                    # Also mark individual call keys so old-style checks still work
                    for c in calls_in_group:
                        await redis.set(f"escalation:{company_id}:{c.id}", str(tier), ex=10800)
                    logger.info(
                        "Escalation tier %d sent for phone %s (company %s, %d calls, %d min old)",
                        tier, phone, company_id, len(calls_in_group), int(age_minutes),
                    )

                    # Tier 3: DM managers (fallback to admins)
                    if tier == 3:
                        await _dm_managers(
                            bot, session, company_id, text, keyboard,
                            phone, company_id_str, lang,
                        )

                except Exception as e:
                    logger.error("Escalation message failed: %s", e)

    except Exception:
        logger.exception("Missed call escalation check failed")
    finally:
        if redis:
            await redis.aclose()


async def _dm_managers(bot, session, company_id, text, keyboard, phone, company_id_str, lang):
    """Send escalation DM to all managers. If no managers, DM admins."""
    from sqlalchemy import select, and_
    from db.models.user import User
    from db.models.enums import RoleEnum
    from aiogram.enums import ParseMode

    # Try managers first
    result = await session.execute(
        select(User).where(
            and_(
                User.company_id == company_id,
                User.role == RoleEnum.COMPANY_MANAGER,
                User.is_active.is_(True),
                User.telegram_user_id.isnot(None),
            )
        )
    )
    managers = result.scalars().all()

    # Fallback to admins if no managers
    if not managers:
        result = await session.execute(
            select(User).where(
                and_(
                    User.company_id == company_id,
                    User.role == RoleEnum.COMPANY_ADMIN,
                    User.is_active.is_(True),
                    User.telegram_user_id.isnot(None),
                )
            )
        )
        managers = result.scalars().all()

    for user in managers:
        try:
            await bot.send_message(
                chat_id=user.telegram_user_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
            logger.info("Escalation DM sent to %s (%s)", user.full_name, user.role.value)
        except Exception as e:
            logger.warning("Escalation DM failed for user %s: %s", user.id, e)


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r'_*[]()~`>#+-=|{}.!'
    return ''.join(('\\' + ch if ch in special else ch) for ch in str(text))


async def escalation_scheduler():
    """
    Background loop: check for unresolved missed calls every CHECK_INTERVAL seconds.

    Start as asyncio.create_task() on app startup.
    """
    logger.info(
        "Missed call escalation scheduler started (every %ds, tiers at %d/%d/%d min)",
        CHECK_INTERVAL, TIER1_MINUTES, TIER2_MINUTES, TIER3_MINUTES,
    )

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            await check_missed_calls()
        except asyncio.CancelledError:
            logger.info("Escalation scheduler stopped")
            break
        except Exception:
            logger.exception("Escalation scheduler error, retrying in 60s")
            await asyncio.sleep(60)
