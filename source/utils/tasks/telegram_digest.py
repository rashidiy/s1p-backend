"""
Daily digest scheduler — sends company stats to Telegram General topic.

Runs as an asyncio background task, triggered daily at configurable time.
Redis lock prevents duplicate sends in multi-instance deployments.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

DIGEST_HOUR = int(os.getenv("TELEGRAM_DIGEST_HOUR", "9"))  # 09:00 default
DIGEST_MINUTE = int(os.getenv("TELEGRAM_DIGEST_MINUTE", "0"))


async def send_daily_digests():
    """
    Query all companies with daily_digest enabled, calculate stats, send digest.

    Each company gets its own digest message in the General topic (or main chat).
    Message is pinned; previous digest is unpinned.
    """
    from db import async_session_factory
    from sqlalchemy import select
    from db.models.telegram_config import TelegramBotConfig
    from utils.services.telegram_service import get_bot, TelegramService
    from utils.services.analytics_service import AnalyticsService
    from utils.services import telegram_i18n as i18n

    bot = get_bot()
    if not bot:
        logger.info("Digest: bot not available, skipping")
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(TelegramBotConfig).where(
                TelegramBotConfig.enabled.is_(True),
                TelegramBotConfig.daily_digest.is_(True),
                TelegramBotConfig.deleted_at.is_(None),
            )
        )
        configs = result.scalars().all()

        today = date.today()
        start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

        for config in configs:
            try:
                lang = config.language or "ru"

                call_stats = await AnalyticsService.get_call_stats(
                    session=session,
                    company_id=config.company_id,
                    from_date=start,
                    to_date=end,
                )
                lead_stats = await AnalyticsService.get_lead_stats(
                    session=session,
                    company_id=config.company_id,
                    from_date=start,
                    to_date=end,
                )

                text = i18n.daily_digest_message(
                    date=today.isoformat(),
                    total_calls=call_stats.total_calls if call_stats else 0,
                    missed_calls=call_stats.missed_calls if call_stats else 0,
                    avg_duration_sec=int(call_stats.avg_duration_seconds) if call_stats and call_stats.avg_duration_seconds else 0,
                    new_leads=lead_stats.total_leads if lead_stats else 0,
                    deals_won=0,
                    deals_lost=0,
                    lang=lang,
                )

                chat_id = config.effective_chat_id
                if not chat_id:
                    continue

                thread_id = config.get_topic_thread_id(None)  # General topic

                from aiogram.enums import ParseMode

                kwargs = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": ParseMode.MARKDOWN_V2,
                }
                if thread_id:
                    kwargs["message_thread_id"] = thread_id

                msg = await bot.send_message(**kwargs)

                # Unpin previous digest, pin new one
                if config.digest_message_id:
                    try:
                        await bot.unpin_chat_message(chat_id=chat_id, message_id=config.digest_message_id)
                    except Exception:
                        pass

                try:
                    await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)
                except Exception:
                    pass

                config.digest_message_id = msg.message_id
                await session.commit()

                logger.info("Digest sent for company %s", config.company_id)

            except Exception:
                logger.exception("Digest failed for company %s", config.company_id)
                continue


async def _wait_until(hour: int, minute: int) -> None:
    """Sleep until the next occurrence of hour:minute UTC."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target.replace(day=target.day + 1)
    delta = (target - now).total_seconds()
    await asyncio.sleep(delta)


async def digest_scheduler():
    """
    Background loop: wait for digest time, acquire Redis lock, send digests.

    Runs forever — start as asyncio.create_task() on app startup.
    """
    logger.info("Digest scheduler started (daily at %02d:%02d UTC)", DIGEST_HOUR, DIGEST_MINUTE)

    while True:
        try:
            await _wait_until(DIGEST_HOUR, DIGEST_MINUTE)

            # Redis lock — prevent duplicate sends in multi-instance
            lock_acquired = False
            try:
                import redis.asyncio as aioredis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                redis = aioredis.from_url(redis_url)
                lock_key = f"tg:digest:lock:{date.today().isoformat()}"
                lock_acquired = await redis.set(lock_key, "1", ex=3600, nx=True)
                await redis.aclose()
            except Exception:
                lock_acquired = True  # Redis down → run anyway (single instance assumed)

            if lock_acquired:
                logger.info("Running daily digests")
                await send_daily_digests()
            else:
                logger.info("Digest lock already held, skipping")

            # Sleep at least 1 hour to avoid re-triggering
            await asyncio.sleep(3600)

        except asyncio.CancelledError:
            logger.info("Digest scheduler stopped")
            break
        except Exception:
            logger.exception("Digest scheduler error, retrying in 60s")
            await asyncio.sleep(60)
