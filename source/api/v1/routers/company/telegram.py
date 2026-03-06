"""
Telegram bot configuration endpoints for company admins.

GET    /telegram/config     — get config for current company
PUT    /telegram/config     — update notification preferences (admin only)
POST   /telegram/connect    — save chat_id for company (admin only)
DELETE /telegram/disconnect — remove chat_id (admin only)
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.telegram_config import TelegramConfig
from api.v1.schemas.telegram import (
    TelegramConfigResponse,
    TelegramConfigUpdateRequest,
    TelegramConnectRequest,
)
from utils.permissions import require_permissions, Permissions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram Integration"])


async def _get_or_create_config(
    company_id, session: AsyncSession
) -> TelegramConfig:
    """Get existing config or create a default one for the company."""
    config = await TelegramConfig.get(session=session, company_id=company_id)
    if not config:
        config = await TelegramConfig.create(
            session=session,
            company_id=company_id,
        )
    return config


@router.get("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_telegram_config(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Get Telegram notification configuration for the current company."""
    config = await _get_or_create_config(admin.company_id, session)
    return TelegramConfigResponse.model_validate(config)


@router.put("/config", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_telegram_config(
    data: TelegramConfigUpdateRequest,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Update Telegram notification preferences (admin only)."""
    config = await _get_or_create_config(admin.company_id, session)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field, value in update_data.items():
        setattr(config, field, value)

    await config.update(session=session)
    return TelegramConfigResponse.model_validate(config)


@router.post("/connect", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def connect_telegram(
    data: TelegramConnectRequest,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Connect a Telegram chat to the company (admin only).

    Saves the chat_id so the bot knows where to send notifications.
    """
    config = await _get_or_create_config(admin.company_id, session)
    config.chat_id = data.chat_id
    config.bot_enabled = True
    await config.update(session=session)

    logger.info(
        "Telegram connected for company %s (chat_id=%s)",
        admin.company_id,
        data.chat_id,
    )
    return TelegramConfigResponse.model_validate(config)


@router.delete("/disconnect", response_model=TelegramConfigResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def disconnect_telegram(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Disconnect Telegram from the company (admin only).

    Removes the chat_id. Notifications will stop.
    """
    config = await _get_or_create_config(admin.company_id, session)

    if config.chat_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram is not connected",
        )

    config.chat_id = None
    config.bot_enabled = False
    await config.update(session=session)

    logger.info("Telegram disconnected for company %s", admin.company_id)
    return TelegramConfigResponse.model_validate(config)
