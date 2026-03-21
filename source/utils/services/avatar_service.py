"""
Avatar service — download Telegram avatars, save uploads, delete files.
"""

import logging
from pathlib import Path

import httpx
from aiogram import Bot

from core.config import TelegramConfig

logger = logging.getLogger(__name__)

AVATARS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "media" / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)


async def download_telegram_avatar(user_id: str, telegram_user_id: int) -> str | None:
    """
    Download a Telegram user's profile photo and save it locally.

    Args:
        user_id: Internal user UUID (used as filename).
        telegram_user_id: Telegram user ID to fetch the photo from.

    Returns:
        Filename (e.g. '{user_id}.jpg') on success, None on failure.
    """
    if not TelegramConfig.BOT_TOKEN:
        return None

    bot = Bot(token=TelegramConfig.BOT_TOKEN)
    try:
        photos = await bot.get_user_profile_photos(user_id=telegram_user_id, limit=1)
        if not photos.total_count or not photos.photos:
            return None

        # Get the largest version of the first photo
        photo = photos.photos[0][-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TelegramConfig.BOT_TOKEN}/{file.file_path}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()

            filename = f"{user_id}.jpg"
            filepath = AVATARS_DIR / filename
            filepath.write_bytes(resp.content)

            return filename
    except Exception:
        logger.exception("Failed to download Telegram avatar for user %s", user_id)
        return None
    finally:
        await bot.session.close()


async def download_telegram_avatar_by_file_id(user_id: str, file_id: str) -> str | None:
    """
    Download a Telegram avatar using a known file_id (skips get_user_profile_photos).

    Args:
        user_id: Internal user UUID (used as filename).
        file_id: Telegram file_id for the avatar photo.

    Returns:
        Filename (e.g. '{user_id}.jpg') on success, None on failure.
    """
    if not file_id or not TelegramConfig.BOT_TOKEN:
        return None

    bot = Bot(token=TelegramConfig.BOT_TOKEN)
    try:
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TelegramConfig.BOT_TOKEN}/{file.file_path}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()

            filename = f"{user_id}.jpg"
            filepath = AVATARS_DIR / filename
            filepath.write_bytes(resp.content)

            return filename
    except Exception:
        logger.exception("Failed to download Telegram avatar by file_id for user %s", user_id)
        return None
    finally:
        await bot.session.close()


def save_uploaded_avatar(user_id: str, file_bytes: bytes) -> str:
    """
    Save an uploaded avatar file to disk.

    Args:
        user_id: Internal user UUID (used as filename).
        file_bytes: Raw image bytes.

    Returns:
        Filename (e.g. '{user_id}.jpg').
    """
    filename = f"{user_id}.jpg"
    filepath = AVATARS_DIR / filename
    filepath.write_bytes(file_bytes)
    return filename


def delete_avatar_file(user_id: str) -> None:
    """
    Remove the avatar file from disk if it exists.

    Args:
        user_id: Internal user UUID.
    """
    filename = f"{user_id}.jpg"
    filepath = AVATARS_DIR / filename
    if filepath.exists():
        filepath.unlink()
