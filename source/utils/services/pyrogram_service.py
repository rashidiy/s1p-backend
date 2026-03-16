"""
Pyrogram userbot service — group creation, bot promotion, invite links.

Uses a single dedicated Telegram account (Premium recommended) via MTProto.
All operations are serialized with asyncio.Lock to prevent FloodWait issues.

Topic creation is delegated to the Bot API (TelegramService.create_forum_topics)
because Pyrogram's high-level create_forum_topic has compatibility issues across forks.
"""

import asyncio
import logging
import random
from typing import Optional

from core.config import PyrogramConfig, TelegramConfig
from utils.services.telegram_constants import TOPIC_NAMES, get_locale

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

    Pyrogram handles: group creation, forum toggle, bot promotion, invite link, topic pinning.
    Bot API handles: topic creation (via TelegramService.create_forum_topics).

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
                        description=f"S1P CRM notifications for {company_name}",
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
                    from pyrogram.types import ChatPermissions
                    from pyrogram.raw.functions.channels import ToggleForum
                    await client.invoke(
                        ToggleForum(
                            channel=await client.resolve_peer(chat_id),
                            enabled=True,
                            tabs=True,
                        )
                    )
                    # Restore member permissions (send messages, media, etc.)
                    await client.set_chat_permissions(chat_id, ChatPermissions(
                        all_perms=True,
                    ))
                    break
                except FloodWait as e:
                    if attempt == 2:
                        raise
                    await _handle_flood(e, "enable_forum")

            # 3. Promote the bot as admin BEFORE creating topics
            #    (bot needs admin rights to create topics via Bot API)
            if bot_username:
                try:
                    bot_username = bot_username.lstrip("@")
                    await setup_bot_admin(client, chat_id, bot_username)
                    await asyncio.sleep(1)  # Wait for Telegram to propagate permissions
                except Exception:
                    logger.warning("Could not promote bot @%s — manual promotion needed", bot_username)

            # 4. Create topics via Bot API (more reliable than Pyrogram's raw API)
            from utils.services.telegram_service import TelegramService
            topic_ids = await TelegramService.create_forum_topics(str(chat_id), lang=lang)

            # 5. Pin topics in order (userbot-only method)
            # Order: Лиды, Пропущенные, Сделки, Звонки (left to right after General)
            try:
                from pyrogram.raw.functions.channels.reorder_pinned_forum_topics import ReorderPinnedForumTopics
                ordered_ids = [topic_ids[k] for k in ["leads", "missed", "deals", "calls"] if k in topic_ids]
                await client.invoke(
                    ReorderPinnedForumTopics(
                        channel=await client.resolve_peer(chat_id),
                        order=ordered_ids,
                        force=True,
                    )
                )
            except Exception:
                logger.debug("Could not pin forum topics for chat %s", chat_id)

            # 6. Generate invite link
            # (group photo is set by TelegramService.create_forum_topics via Bot API)
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


async def delete_group(chat_id: int) -> bool:
    """
    Delete a supergroup via Pyrogram userbot.

    The userbot must join the group first (if not already a member),
    then delete it. Returns True on success, False on failure.
    """
    async with _lock:
        client = await _get_client()
        if not client:
            return False

        try:
            from pyrogram.errors import FloodWait

            # Join the group if not already a member (needed to delete)
            try:
                await client.get_chat(chat_id)
            except Exception:
                # Not in cache — try to join via bot's invite link
                from utils.services.telegram_service import get_bot
                bot = get_bot()
                if bot:
                    try:
                        result = await bot.create_chat_invite_link(
                            chat_id=chat_id,
                            name="userbot_delete",
                        )
                        await client.join_chat(result.invite_link)
                    except Exception:
                        logger.debug("Could not join group %s for deletion", chat_id)
                        return False

            await client.delete_supergroup(chat_id)
            logger.info("Deleted Telegram group %s", chat_id)
            return True

        except FloodWait as e:
            logger.warning("FloodWait deleting group %s: %ss", chat_id, e.value)
            return False
        except Exception:
            logger.exception("Failed to delete Telegram group %s", chat_id)
            return False


async def shutdown() -> None:
    """Gracefully disconnect the Pyrogram client."""
    global _client
    if _client and _client.is_connected:
        await _client.stop()
        logger.info("Pyrogram client disconnected")
    _client = None
