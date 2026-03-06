"""
Telegram integration schemas
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TelegramConfigResponse(BaseModel):
    """Telegram config read response"""
    id: UUID
    company_id: UUID
    chat_id: Optional[int] = None
    bot_enabled: bool
    notify_completed_calls: bool
    notify_missed_calls: bool
    notify_new_leads: bool
    notify_deal_stage_change: bool
    is_connected: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TelegramConfigUpdateRequest(BaseModel):
    """Update notification preferences"""
    bot_enabled: Optional[bool] = None
    notify_completed_calls: Optional[bool] = None
    notify_missed_calls: Optional[bool] = None
    notify_new_leads: Optional[bool] = None
    notify_deal_stage_change: Optional[bool] = None


class TelegramConnectRequest(BaseModel):
    """Connect a Telegram chat to the company"""
    chat_id: int
