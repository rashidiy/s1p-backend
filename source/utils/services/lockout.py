"""
Account lockout service using Redis.

Tracks failed login attempts per email and locks accounts after
too many failures within a time window.

Keys:
- failed_login:{email}  — counter of failed attempts (TTL: 60s)
- locked:{email}        — lockout flag (TTL: 900s / 15 min)
"""

import logging
import os
from typing import Optional

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger("s1p.lockout")

MAX_FAILED_ATTEMPTS = 5
FAILED_WINDOW_TTL = 60       # seconds — window for counting failures
LOCKOUT_TTL = 900            # seconds — 15 minute lockout


_redis_client = None


async def _get_redis():
    """Get or create a Redis client for lockout operations."""
    global _redis_client
    if _redis_client is None:
        if not REDIS_AVAILABLE:
            return None
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = aioredis.from_url(
            redis_url, encoding="utf-8", decode_responses=True
        )
    return _redis_client


async def is_locked(email: str) -> bool:
    """Check if the account is currently locked out."""
    client = await _get_redis()
    if client is None:
        logger.warning(
            "Redis unavailable — account lockout is disabled. "
            "Login attempts will not be rate-limited."
        )
        return False
    val = await client.get(f"locked:{email}")
    return val is not None


async def record_failed_login(email: str) -> None:
    """
    Increment failed login counter for an email.

    If the counter reaches MAX_FAILED_ATTEMPTS, set a lockout key.
    """
    client = await _get_redis()
    if client is None:
        logger.warning(
            "Redis unavailable — failed login attempt not recorded for %s",
            email,
        )
        return

    key = f"failed_login:{email}"
    count = await client.incr(key)

    # Set TTL on first failure (incr creates key with no expiry)
    if count == 1:
        await client.expire(key, FAILED_WINDOW_TTL)

    if count >= MAX_FAILED_ATTEMPTS:
        await client.setex(f"locked:{email}", LOCKOUT_TTL, "1")
        # Reset the failure counter since lockout is now active
        await client.delete(key)


async def clear_failed_logins(email: str) -> None:
    """Clear failed login counter on successful login."""
    client = await _get_redis()
    if client is None:
        return
    await client.delete(f"failed_login:{email}")
