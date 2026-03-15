"""
Pyrogram userbot service — group creation, bot promotion, invite links.

Uses a single dedicated Telegram account (Premium recommended) via MTProto.
All operations are serialized with asyncio.Lock to prevent FloodWait issues.
"""

import asyncio
import logging
import random
from typing import Optional

from core.config import PyrogramConfig, TelegramConfig
from utils.services.telegram_constants import TOPIC_NAMES, TOPIC_EMOJI, get_locale

logger = logging.getLogger(__name__)

# Singleton client + lock
_client = None
_lock = asyncio.Lock()


async def _get_client():
    """Get or create the shared Pyrogram client. Returns None if not configured."""
    global _client

    if not PyrogramConfig.ENABLED:
        return None
    if not PyrogramConfig.SESSION_STRING:
        logger.warning("Pyrogram enabled but SESSION_STRING not set")
        return None

    if _client is not None:
        if _client.is_connected:
            return _client

    try:
        from pyrogram import Client

        _client = Client(
            name="s1p_userbot",
            api_id=PyrogramConfig.API_ID,
            api_hash=PyrogramConfig.API_HASH,
            session_string=PyrogramConfig.SESSION_STRING,
            in_memory=True,
        )
        await _client.start()
        me = await _client.get_me()
        logger.info("Pyrogram userbot connected as @%s (id=%s)", me.username, me.id)
        return _client
    except Exception:
        logger.exception("Failed to start Pyrogram client")
        _client = None
        return None


async def _handle_flood(e, operation: str) -> None:
    """Handle FloodWait with exponential backoff + jitter."""
    wait = getattr(e, 'value', 30) + random.uniform(1, 5)
    logger.warning("FloodWait on %s — sleeping %.1fs", operation, wait)
    await asyncio.sleep(wait)


def is_available() -> bool:
    """Check if the Pyrogram userbot is configured (not necessarily connected)."""
    return PyrogramConfig.ENABLED and bool(PyrogramConfig.SESSION_STRING)


async def create_group(
    company_name: str,
    bot_username: str | None = None,
    lang: str = "ru",
) -> dict:
    """
    Create a supergroup with forum topics enabled.

    Returns: {
        "group_chat_id": int,
        "topic_ids": {"calls": int, "missed": int, "leads": int, "deals": int, "general": int},
        "invite_link": str,
        "group_name": str,
    }

    Raises RuntimeError if creation fails.
    """
    async with _lock:
        client = await _get_client()
        if not client:
            raise RuntimeError("Pyrogram userbot not available")

        locale = get_locale(lang)
        group_name = f"S1P — {company_name}"

        try:
            from pyrogram.errors import FloodWait

            # 1. Create supergroup
            for attempt in range(3):
                try:
                    group = await client.create_supergroup(
                        title=group_name,
                        about=f"S1P CRM notifications for {company_name}",
                    )
                    break
                except FloodWait as e:
                    if attempt == 2:
                        raise
                    await _handle_flood(e, "create_supergroup")
            else:
                raise RuntimeError("Failed to create supergroup after retries")

            chat_id = group.id

            # 2. Enable forum/topics
            for attempt in range(3):
                try:
                    await client.set_chat_permissions(chat_id, client.types.ChatPermissions())
                    # Toggle forum mode
                    await client.invoke(
                        client.raw.functions.channels.ToggleForum(
                            channel=await client.resolve_peer(chat_id),
                            enabled=True,
                        )
                    )
                    break
                except FloodWait as e:
                    if attempt == 2:
                        raise
                    await _handle_flood(e, "enable_forum")

            # 3. Create topics
            topic_names = TOPIC_NAMES[locale]
            topic_ids = {}

            for topic_key in ["calls", "missed", "leads", "deals"]:
                emoji = TOPIC_EMOJI[topic_key]
                name = f"{emoji} {topic_names[topic_key]}"

                for attempt in range(3):
                    try:
                        result = await client.create_forum_topic(
                            chat_id=chat_id,
                            title=name,
                        )
                        topic_ids[topic_key] = result.id
                        break
                    except FloodWait as e:
                        if attempt == 2:
                            raise
                        await _handle_flood(e, f"create_topic:{topic_key}")

                await asyncio.sleep(0.5)  # Rate limit safety

            # "General" topic is always thread_id=1
            topic_ids["general"] = 1

            # 4. Promote the bot as admin
            if bot_username:
                try:
                    bot_username = bot_username.lstrip("@")
                    await setup_bot_admin(client, chat_id, bot_username)
                except Exception:
                    logger.warning("Could not promote bot @%s — manual promotion needed", bot_username)

            # 5. Generate invite link
            invite = await generate_invite_link(client, chat_id)

            return {
                "group_chat_id": chat_id,
                "topic_ids": topic_ids,
                "invite_link": invite,
                "group_name": group_name,
            }

        except Exception as e:
            logger.exception("Failed to create group for %s", company_name)
            raise RuntimeError(f"Group creation failed: {e}") from e


async def setup_bot_admin(client, chat_id: int, bot_username: str) -> None:
    """Promote a bot to admin in the group with necessary permissions."""
    from pyrogram.types import ChatPrivileges

    await client.promote_chat_member(
        chat_id=chat_id,
        user_id=bot_username,
        privileges=ChatPrivileges(
            can_manage_chat=True,
            can_post_messages=True,
            can_edit_messages=True,
            can_delete_messages=True,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_topics=True,
        ),
    )
    logger.info("Bot @%s promoted to admin in chat %s", bot_username, chat_id)


async def generate_invite_link(client, chat_id: int) -> str:
    """Generate a permanent invite link for the group."""
    link = await client.create_chat_invite_link(
        chat_id=chat_id,
        name="S1P Setup",
    )
    return link.invite_link


async def shutdown() -> None:
    """Gracefully disconnect the Pyrogram client."""
    global _client
    if _client and _client.is_connected:
        await _client.stop()
        logger.info("Pyrogram client disconnected")
    _client = None
