"""
Telegram bot configuration and management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, Dict

from db import get_session
from db.models.user import User
from db.models.telegram_config import TelegramBotConfig
from utils.permissions import require_permissions, Permissions
from utils.services.telegram_service import TelegramService

router = APIRouter(prefix="/telegram", tags=["Telegram"])


# Schemas

class TelegramConfigCreate(BaseModel):
    chat_id: str = Field(..., description="Telegram chat/group ID")
    notification_filters: Optional[Dict[str, bool]] = Field(
        default=None,
        description="Event filters: call_completed, call_missed, new_lead, deal_stage_change"
    )
    enabled: bool = True


class TelegramConfigUpdate(BaseModel):
    chat_id: Optional[str] = None
    notification_filters: Optional[Dict[str, bool]] = None
    enabled: Optional[bool] = None


class TelegramConfigResponse(BaseModel):
    id: str
    company_id: str
    chat_id: str
    notification_filters: dict
    enabled: bool

    class Config:
        from_attributes = True


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

    return TelegramConfigResponse(
        id=str(config.id),
        company_id=str(config.company_id),
        chat_id=config.chat_id,
        notification_filters=config.notification_filters or {},
        enabled=config.enabled
    )


@router.post("/config", response_model=TelegramConfigResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_telegram_config(
    data: TelegramConfigCreate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Create or update Telegram bot configuration for the company"""
    # Check if config already exists
    existing = await TelegramBotConfig.get(
        session=session,
        company_id=user.company_id
    )

    default_filters = {
        "call_completed": True,
        "call_missed": True,
        "new_lead": True,
        "deal_stage_change": True,
    }

    if existing:
        # Update existing
        existing.chat_id = data.chat_id
        existing.enabled = data.enabled
        if data.notification_filters is not None:
            existing.notification_filters = data.notification_filters
        existing.deleted_at = None  # Re-enable if soft-deleted
        await existing.update(session=session)
        config = existing
    else:
        # Create new
        config = await TelegramBotConfig.create(
            session=session,
            company_id=user.company_id,
            chat_id=data.chat_id,
            notification_filters=data.notification_filters or default_filters,
            enabled=data.enabled
        )

    return TelegramConfigResponse(
        id=str(config.id),
        company_id=str(config.company_id),
        chat_id=config.chat_id,
        notification_filters=config.notification_filters or {},
        enabled=config.enabled
    )


@router.put("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_telegram_config(
    data: TelegramConfigUpdate,
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

    if data.chat_id is not None:
        config.chat_id = data.chat_id
    if data.notification_filters is not None:
        config.notification_filters = data.notification_filters
    if data.enabled is not None:
        config.enabled = data.enabled

    await config.update(session=session)

    return TelegramConfigResponse(
        id=str(config.id),
        company_id=str(config.company_id),
        chat_id=config.chat_id,
        notification_filters=config.notification_filters or {},
        enabled=config.enabled
    )


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
