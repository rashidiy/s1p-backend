"""
Orphan call cleanup — marks stale call records with NULL state as FAILED.

Calls created by /number, /external, /tree that never receive webhook events
stay with NULL state forever (SIP offline, first leg dropped, etc.).
Runs every 120 seconds, cleans up calls older than 5 minutes with no state.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 120  # seconds
STALE_THRESHOLD_MINUTES = 5


async def cleanup_orphan_calls():
    """Find call records with NULL state older than threshold and mark as FAILED."""
    from sqlalchemy import update, and_
    from db import async_session_factory
    from db.models.call_event import CallEvent
    from db.models.enums import CallStatusEnum

    try:
        async with async_session_factory() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)

            result = await session.execute(
                update(CallEvent).where(
                    and_(
                        CallEvent.state.is_(None),
                        CallEvent.created_at < cutoff,
                    )
                ).values(state=CallStatusEnum.NOANSWER)
            )

            if result.rowcount > 0:
                await session.commit()
                logger.info("Orphan cleanup: marked %d stale calls as NOANSWER", result.rowcount)

    except Exception:
        logger.exception("Orphan call cleanup failed")


async def orphan_cleanup_scheduler():
    """Background loop: clean up orphan calls every CLEANUP_INTERVAL seconds."""
    logger.info("Orphan call cleanup scheduler started (every %ds, threshold %dm)",
                CLEANUP_INTERVAL, STALE_THRESHOLD_MINUTES)

    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            await cleanup_orphan_calls()
        except asyncio.CancelledError:
            logger.info("Orphan cleanup scheduler stopped")
            break
        except Exception:
            logger.exception("Orphan cleanup scheduler error, retrying in 120s")
            await asyncio.sleep(120)
