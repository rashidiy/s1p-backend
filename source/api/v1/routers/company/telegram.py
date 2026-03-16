"""
Telegram bot configuration and management endpoints

V2 adds: POST /setup, GET /setup/status, POST /setup/manual
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.telegram_config import TelegramBotConfig
from utils.permissions import require_permissions, Permissions
from utils.services.telegram_service import TelegramService
from api.v1.schemas.telegram import (
    TelegramConfigResponse,
    TelegramConfigCreateRequest,
    TelegramConfigUpdateRequest,
    TelegramSetupRequest,
    TelegramSetupStatusResponse,
    TelegramManualSetupRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])

limiter = Limiter(key_func=get_remote_address)


# ── Existing config endpoints ────────────────────────────────────

@router.get("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_telegram_config(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get Telegram bot configuration

    Returns the current notification settings, chat ID, and setup status.
    Returns 404 if Telegram is not configured for this company.
    """
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    return TelegramConfigResponse.from_model(config)


@router.post("/config", response_model=TelegramConfigResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_telegram_config(
    data: TelegramConfigCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create Telegram bot configuration

    Sets up Telegram notifications for the company. If a configuration already exists,
    it will be updated. Provide the chat_id obtained from the bot's /start command.
    """
    existing = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    filters = data.to_notification_filters()

    if existing:
        existing.chat_id = data.chat_id
        existing.enabled = data.bot_enabled
        existing.notification_filters = filters
        existing.deleted_at = None  # Re-enable if soft-deleted
        await existing.update(session=session)
        config = existing
    else:
        config = await TelegramBotConfig.create(
            session=session,
            company_id=user.company_id,
            chat_id=data.chat_id,
            notification_filters=filters,
            enabled=data.bot_enabled,
        )

    return TelegramConfigResponse.from_model(config)


@router.put("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_telegram_config(
    data: TelegramConfigUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update Telegram bot configuration

    Modify notification filters, language, recording forwarding, and other settings.
    Supports partial updates — only provided fields are changed.
    """
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    model_fields = data.to_model_fields()

    if "enabled" in model_fields:
        config.enabled = model_fields["enabled"]

    if "notification_filters" in model_fields:
        # Merge partial updates into existing filters
        # Must reassign (not mutate in-place) so SQLAlchemy detects the change
        current_filters = dict(config.notification_filters or {})
        current_filters.update(model_fields["notification_filters"])
        config.notification_filters = current_filters

    # V2 settings
    old_language = config.language
    for field in ("language", "send_recordings", "daily_digest", "dm_notifications"):
        if field in model_fields:
            setattr(config, field, model_fields[field])

    await config.update(session=session)

    # Rename forum topics when language changes
    new_language = model_fields.get("language")
    if new_language and new_language != old_language and config.topic_ids and config.effective_chat_id:
        try:
            await TelegramService.rename_forum_topics(
                config.effective_chat_id, config.topic_ids, new_language
            )
        except Exception:
            logger.debug("Failed to rename topics on language change")

    return TelegramConfigResponse.from_model(config)


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_telegram_config(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Delete Telegram bot configuration

    Removes the configuration and destroys the associated Telegram group (if created via automated setup).
    This action cannot be undone. Requires SETTINGS_MANAGE permission.
    """
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    # Destroy the Telegram group via Pyrogram userbot
    group_chat_id = config.group_chat_id
    if group_chat_id:
        from utils.services import pyrogram_service
        if pyrogram_service.is_available():
            deleted = await pyrogram_service.delete_group(group_chat_id)
            if not deleted:
                logger.warning("Could not delete Telegram group %s, proceeding with config removal", group_chat_id)

    # Hard-delete the config row (not soft-delete) so it can be recreated
    await session.delete(config)
    await session.commit()
    return None


@router.post("/test")
@limiter.limit("5/minute")
@require_permissions(Permissions.SETTINGS_MANAGE)
async def send_test_message(
    request: Request,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Send a test notification

    Sends a test message to the configured Telegram chat to verify the bot is working.
    Rate limited to 5 requests per minute.
    """
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    chat_id = config.effective_chat_id or config.chat_id
    success = await TelegramService.send_test_message(chat_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send test message. Check bot token and chat_id."
        )

    return {"success": True, "message": "Test message sent"}


# ── V2 Setup endpoints ──────────────────────────────────────────

@router.post("/setup", response_model=TelegramSetupStatusResponse)
@limiter.limit("3/minute")
@require_permissions(Permissions.SETTINGS_MANAGE)
async def setup_telegram_group(
    request: Request,
    data: TelegramSetupRequest,
    background_tasks: BackgroundTasks,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Start automated Telegram group setup.

    Creates supergroup → enables topics → promotes bot → generates invite link.
    Runs async — poll GET /setup/status for progress.
    """
    from utils.services import pyrogram_service
    from core.config import TelegramConfig as TgCfg

    if not pyrogram_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Automated setup not available. Use manual setup."
        )

    # Get or create config
    config = await TelegramBotConfig.get(session=session, company_id=user.company_id)
    if not config:
        config = await TelegramBotConfig.create(
            session=session,
            company_id=user.company_id,
            chat_id="",
            enabled=True,
        )

    if config.setup_status == "creating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup already in progress"
        )

    # Mark as creating
    config.setup_status = "creating"
    config.setup_error = None
    config.language = data.language
    await config.update(session=session)

    # Run setup in background
    background_tasks.add_task(
        _run_setup,
        company_id=user.company_id,
        company_name=data.company_name,
        language=data.language,
        bot_username=TgCfg.BOT_USERNAME,
    )

    return TelegramSetupStatusResponse(
        setup_status="creating",
        group_name=f"S1P — {data.company_name}",
    )


async def _run_setup(company_id, company_name: str, language: str, bot_username: str):
    """Background task: create group via Pyrogram, update config on completion."""
    from utils.services import pyrogram_service
    from db import async_session_factory

    async with async_session_factory() as session:
        try:
            result = await pyrogram_service.create_group(
                company_name=company_name,
                bot_username=bot_username,
                lang=language,
            )

            config = await TelegramBotConfig.get(session=session, company_id=company_id)
            if not config:
                return

            config.group_chat_id = result["group_chat_id"]
            config.topic_ids = result["topic_ids"]
            config.invite_link = result["invite_link"]
            config.group_name = result["group_name"]
            config.setup_status = "ready"
            config.setup_error = None
            await config.update(session=session)

            logger.info("Telegram group setup complete for company %s", company_id)

        except Exception as e:
            logger.exception("Telegram group setup failed for company %s", company_id)
            try:
                config = await TelegramBotConfig.get(session=session, company_id=company_id)
                if config:
                    config.setup_status = "failed"
                    config.setup_error = str(e)[:500]
                    await config.update(session=session)
            except Exception:
                logger.exception("Failed to update setup_error")


@router.get("/setup/status", response_model=TelegramSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_setup_status(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get Telegram setup status

    Poll this endpoint after starting automated setup to track progress.
    Returns status (not_started, creating, ready, failed) and invite link when ready.
    """
    config = await TelegramBotConfig.get(session=session, company_id=user.company_id)

    if not config:
        return TelegramSetupStatusResponse(setup_status="not_started")

    return TelegramSetupStatusResponse(
        setup_status=config.setup_status or "not_started",
        setup_error=config.setup_error,
        invite_link=config.invite_link,
        group_name=config.group_name,
        group_chat_id=config.group_chat_id,
    )


@router.post("/setup/manual", response_model=TelegramSetupStatusResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def manual_setup(
    data: TelegramManualSetupRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Manual setup fallback — admin provides chat_id, bot creates topics.

    Requires: bot already added to the group as admin with topic management.
    """
    # Get or create config
    config = await TelegramBotConfig.get(session=session, company_id=user.company_id)
    if not config:
        config = await TelegramBotConfig.create(
            session=session,
            company_id=user.company_id,
            chat_id=data.chat_id,
            enabled=True,
        )
    else:
        config.chat_id = data.chat_id

    try:
        # Try to create topics via Bot API
        lang = config.language if config else "ru"
        topic_ids = await TelegramService.create_forum_topics(data.chat_id, lang=lang)

        config.group_chat_id = int(data.chat_id)
        config.topic_ids = topic_ids
        config.setup_status = "ready"
        config.setup_error = None
        await config.update(session=session)

        return TelegramSetupStatusResponse(
            setup_status="ready",
            group_chat_id=config.group_chat_id,
        )

    except Exception as e:
        # Topics failed — still usable without topics (sends to main chat)
        logger.warning("Topic creation failed for chat %s: %s", data.chat_id, e)

        config.setup_status = "manual"
        config.setup_error = f"Topics not created: {e}"
        await config.update(session=session)

        return TelegramSetupStatusResponse(
            setup_status="manual",
            setup_error=config.setup_error,
            group_chat_id=int(data.chat_id) if data.chat_id.lstrip('-').isdigit() else None,
        )
