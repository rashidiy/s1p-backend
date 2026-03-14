"""
Telegram bot configuration and management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
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
)

router = APIRouter(prefix="/telegram", tags=["Telegram"])


# Endpoints

@router.get("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_telegram_config(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Get company's Telegram bot configuration"""
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
    """Create or update Telegram bot configuration for the company"""
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
    """Update Telegram bot configuration"""
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
        current_filters = config.notification_filters or {}
        current_filters.update(model_fields["notification_filters"])
        config.notification_filters = current_filters

    await config.update(session=session)

    return TelegramConfigResponse.from_model(config)


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_telegram_config(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Delete Telegram bot configuration"""
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    await config.delete(session=session)
    return None


@router.post("/test")
@require_permissions(Permissions.SETTINGS_MANAGE)
async def send_test_message(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Send a test notification to verify bot is working"""
    config = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telegram bot not configured"
        )

    success = await TelegramService.send_test_message(config.chat_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send test message. Check bot token and chat_id."
        )

    return {"success": True, "message": "Test message sent"}
