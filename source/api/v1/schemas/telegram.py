"""
Telegram integration schemas

Flattens the model's JSONB notification_filters into individual boolean fields
to match what the frontend expects.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, model_validator


class TelegramConfigResponse(BaseModel):
    """Telegram config read response — flat boolean fields for frontend."""
    id: str
    company_id: str
    chat_id: Optional[str] = None
    bot_enabled: bool
    notify_completed_calls: bool
    notify_missed_calls: bool
    notify_new_leads: bool
    notify_deal_stage_change: bool

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, config) -> "TelegramConfigResponse":
        """Build response from TelegramBotConfig model instance."""
        filters = config.notification_filters or {}
        return cls(
            id=str(config.id),
            company_id=str(config.company_id),
            chat_id=config.chat_id,
            bot_enabled=config.enabled,
            notify_completed_calls=filters.get("call_completed", False),
            notify_missed_calls=filters.get("call_missed", False),
            notify_new_leads=filters.get("new_lead", False),
            notify_deal_stage_change=filters.get("deal_stage_change", False),
        )


class TelegramConfigUpdateRequest(BaseModel):
    """Update notification preferences — flat boolean fields from frontend."""
    bot_enabled: Optional[bool] = None
    notify_completed_calls: Optional[bool] = None
    notify_missed_calls: Optional[bool] = None
    notify_new_leads: Optional[bool] = None
    notify_deal_stage_change: Optional[bool] = None

    def to_model_fields(self) -> dict:
        """Convert flat booleans to model fields (enabled + notification_filters)."""
        result = {}
        if self.bot_enabled is not None:
            result["enabled"] = self.bot_enabled

        filters = {}
        if self.notify_completed_calls is not None:
            filters["call_completed"] = self.notify_completed_calls
        if self.notify_missed_calls is not None:
            filters["call_missed"] = self.notify_missed_calls
        if self.notify_new_leads is not None:
            filters["new_lead"] = self.notify_new_leads
        if self.notify_deal_stage_change is not None:
            filters["deal_stage_change"] = self.notify_deal_stage_change

        if filters:
            result["notification_filters"] = filters
        return result


class TelegramConfigCreateRequest(BaseModel):
    """Connect a Telegram chat to the company."""
    chat_id: str
    bot_enabled: bool = True
    notify_completed_calls: bool = True
    notify_missed_calls: bool = True
    notify_new_leads: bool = True
    notify_deal_stage_change: bool = True

    def to_notification_filters(self) -> dict:
        """Convert flat booleans to JSONB notification_filters."""
        return {
            "call_completed": self.notify_completed_calls,
            "call_missed": self.notify_missed_calls,
            "new_lead": self.notify_new_leads,
            "deal_stage_change": self.notify_deal_stage_change,
        }
