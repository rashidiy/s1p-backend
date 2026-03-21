"""
Unified webhook handler for all telephony providers
"""

import logging
from uuid import UUID
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import WebhookConfig
from db import get_session
from db.base import AsyncDatabaseSession
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.user import User
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.enums import ProviderEnum, CallStatusEnum
from utils.services.telephony import ProviderFactory
from utils.services.webhook import fire_webhook_event
from api.v1.routers.company.calls.common import next_call_number

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

limiter = Limiter(key_func=get_remote_address)

# Terminal call states — once set, RINGING should not overwrite
_TERMINAL_STATES = {
    CallStatusEnum.ANSWER, CallStatusEnum.BUSY, CallStatusEnum.NOANSWER,
    CallStatusEnum.CANCEL, CallStatusEnum.CONGESTION, CallStatusEnum.CHANUNAVAIL,
}


class WebhookCallData(BaseModel):
    """
    Strict Pydantic schema for normalized webhook call data.
    Extra fields are forbidden to prevent unexpected data injection.
    """
    model_config = ConfigDict(extra="forbid")

    provider_call_id: str
    phone_1: Optional[str] = None
    phone_2: Optional[str] = None
    state: Optional[str] = None
    billing_sec: Optional[int] = None
    waiting_sec: Optional[int] = None
    record_url: Optional[str] = None
    call_start_timestamp: Optional[int] = None
    call_end_timestamp: Optional[int] = None
    call_answer_timestamp: Optional[int] = None
    direction: Optional[str] = None
    attempts: Optional[int] = None
    company_number: Optional[str] = None
    order_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    operator_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None

    # Sipuni webhook event fields
    scheme_name: Optional[str] = None
    scheme_number: Optional[str] = None
    transfer_from: Optional[str] = None
    last_called: Optional[str] = None
    is_transfer: Optional[bool] = None

    # Fields that the provider handler may include but are set later by the router
    company_id: Optional[UUID] = None
    provider_type: Optional[str] = None
    call_type: Optional[str] = None


def validate_webhook_ip(request: Request, provider_type: ProviderEnum) -> bool:
    """
    Validate webhook request IP against provider whitelist

    Args:
        request: FastAPI request object
        provider_type: The telephony provider type

    Returns:
        True if IP is allowed, False otherwise
    """
    # If IP whitelisting is disabled, allow all
    if not WebhookConfig.WEBHOOK_IP_WHITELIST_ENABLED:
        return True

    # Get client IP — check proxy headers first, then direct connection
    client_ip = (
        request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )
    if not client_ip:
        return False

    # Check against provider-specific whitelist
    allowed_ips: List[str] = []
    if provider_type == ProviderEnum.SIPUNI:
        allowed_ips = WebhookConfig.SIPUNI_ALLOWED_IPS
    elif provider_type == ProviderEnum.BINOTEL:
        allowed_ips = WebhookConfig.BINOTEL_ALLOWED_IPS

    # If no IPs configured for provider, deny access
    if not allowed_ips:
        return False

    # Check if client IP is in whitelist
    return client_ip in allowed_ips


async def _validate_entity_ownership(
    session: AsyncSession,
    company_id: UUID,
    operator_id: Optional[UUID],
    contact_id: Optional[UUID],
    lead_id: Optional[UUID],
) -> None:
    """
    Validate that referenced entities belong to the same company.
    Raises HTTPException if any entity doesn't belong to the company.
    """
    if operator_id:
        result = await session.execute(
            select(User.id).where(
                User.company_id == company_id,
                User.id == operator_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Operator does not belong to this company",
            )

    if contact_id:
        result = await session.execute(
            select(Contact.id).where(
                Contact.company_id == company_id,
                Contact.id == contact_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact does not belong to this company",
            )

    if lead_id:
        result = await session.execute(
            select(Lead.id).where(
                Lead.company_id == company_id,
                Lead.id == lead_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead does not belong to this company",
            )


@router.get("/{token}")
@limiter.limit("60/minute")
async def handle_webhook(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Unified webhook endpoint for all telephony providers

    Routes webhook to the correct provider handler based on company configuration.
    Providers normalize their webhook data into a unified format.

    Security:
    - Validates webhook token
    - Validates source IP against provider whitelist
    - Validates provider-specific authentication
    - Strict Pydantic schema validation on normalized payload
    - Entity ownership validation (operator, contact, lead)
    """
    # GET request: payload comes from query parameters
    payload = dict(request.query_params)

    # Find company by webhook token
    company = await Company.get(session=session, webhook_token=token)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid webhook token"
        )
    # Validate source IP against provider whitelist
    if not validate_webhook_ip(request, company.provider_type):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: IP not whitelisted for this provider"
        )

    try:
        # Create provider instance
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        # Validate webhook authentication
        headers = dict(request.headers)
        if not await provider.validate_webhook_auth(payload, headers):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Webhook authentication failed"
            )

        # Handle webhook (provider-specific logic, returns normalized data)
        call_data = await provider.handle_webhook(payload, headers)

        if not call_data:
            # Webhook was valid but not a call event we care about
            return {"status": "ignored", "message": "Event type not handled"}

        # Extract _event_type before schema validation (not a DB field)
        event_type = call_data.pop('_event_type', None)

        # Validate normalized data against strict schema (extra='forbid')
        try:
            validated = WebhookCallData(**call_data)
        except Exception as e:
            logger.warning(
                f"Webhook payload validation failed for company {company.id}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid webhook payload",
            )

        # Convert to dict, excluding None values and fields we'll set manually
        call_data = validated.model_dump(exclude_none=True)

        # Add company_id to call data
        call_data['company_id'] = company.id
        call_data['provider_type'] = company.provider_type

        # Validate entity ownership before creating/updating
        await _validate_entity_ownership(
            session=session,
            company_id=company.id,
            operator_id=call_data.get('operator_id'),
            contact_id=call_data.get('contact_id'),
            lead_id=call_data.get('lead_id'),
        )

        # Check if call event already exists (for updates)
        existing_call = await CallEvent.get(
            session=session,
            company_id=company.id,
            provider_type=company.provider_type,
            provider_call_id=call_data['provider_call_id']
        )

        if existing_call:
            # Don't overwrite phones set by call endpoint with SIP extensions from webhook
            if existing_call.phone_1 and 'phone_1' in call_data:
                call_data.pop('phone_1')
            if existing_call.phone_2 and 'phone_2' in call_data:
                call_data.pop('phone_2')

            # Guard: don't let earlier events overwrite terminal states with RINGING
            existing_state = existing_call.state
            incoming_state = call_data.get('state')
            if (
                existing_state in _TERMINAL_STATES
                and incoming_state
                and incoming_state == CallStatusEnum.RINGING.value
            ):
                call_data.pop('state', None)

            # Update existing call event (company_id for defense-in-depth)
            await CallEvent.update_by(
                session=session,
                values=call_data,
                id=existing_call.id,
                company_id=company.id,
            )

            # Fire notifications based on event type
            _schedule_notifications(
                background_tasks, session, company.id,
                call_data, existing_call.id, event_type,
            )
            return {"status": "updated", "call_id": existing_call.id}
        else:
            # Assign company-scoped id for new events
            call_data['id'] = await next_call_number(session, company.id)
            call_event = await CallEvent.create(session=session, **call_data)

            # Fire notifications based on event type
            _schedule_notifications(
                background_tasks, session, company.id,
                call_data, call_event.id, event_type,
            )
            return {"status": "created", "call_id": call_event.id}

    except HTTPException:
        raise
    except Exception as e:
        # Log the error but return 200 to prevent provider retries
        logger.error(f"Webhook processing error for company {company.id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Internal processing error"}


def _schedule_notifications(
    background_tasks: BackgroundTasks,
    session: AsyncSession,
    company_id: UUID,
    call_data: dict,
    call_id: int,
    event_type: Optional[str],
):
    """Schedule outbound webhooks and Telegram notifications based on event type."""

    if event_type == "call_started":
        # Fire call.started outbound webhook, no Telegram (too noisy)
        background_tasks.add_task(
            _fire_call_webhook, session, company_id, call_data, call_id,
            webhook_event="call.started",
        )

    elif event_type == "call_answered":
        # No notifications for answer event
        pass

    elif event_type == "call_transferred":
        # Fire call.transferred outbound webhook, no Telegram yet
        background_tasks.add_task(
            _fire_call_webhook, session, company_id, call_data, call_id,
            webhook_event="call.transferred",
        )

    elif event_type == "call_ended":
        # Final event — fire outbound webhook + Telegram notification
        background_tasks.add_task(
            _send_call_notification, company_id, call_data
        )
        background_tasks.add_task(
            _fire_call_webhook, session, company_id, call_data, call_id,
        )

    else:
        # Legacy path (Binotel or unknown) — keep existing behavior
        background_tasks.add_task(
            _send_call_notification, company_id, call_data
        )
        background_tasks.add_task(
            _fire_call_webhook, session, company_id, call_data, call_id,
        )


async def _fire_call_webhook(
    session, company_id, call_data: dict, call_id, webhook_event: Optional[str] = None
):
    """Fire outbound webhook for call events."""
    state = call_data.get('state')

    # If explicit webhook_event provided, use it
    if webhook_event:
        event_type = webhook_event
    elif not state:
        return
    else:
        is_answered = state == CallStatusEnum.ANSWER or (isinstance(state, str) and state == "ANSWER")
        is_missed = state in (CallStatusEnum.NOANSWER, CallStatusEnum.BUSY, CallStatusEnum.CANCEL) or (
            isinstance(state, str) and state in ("NOANSWER", "BUSY", "CANCEL")
        )

        if not is_answered and not is_missed:
            return

        event_type = "call.completed" if is_answered else "call.missed"

    direction = call_data.get('direction')
    if hasattr(direction, 'value'):
        direction = direction.value

    try:
        await fire_webhook_event(
            company_id=company_id,
            event_type=event_type,
            data={
                "id": call_id,
                "phone_1": call_data.get('phone_1'),
                "phone_2": call_data.get('phone_2'),
                "direction": str(direction) if direction else None,
                "duration": call_data.get('billing_sec'),
                "state": state.value if hasattr(state, 'value') else str(state) if state else None,
                "scheme_name": call_data.get('scheme_name'),
                "is_transfer": call_data.get('is_transfer', False),
            },
            session=session,
        )
    except Exception as e:
        logger.error(f"Outbound webhook fire failed for call event: {e}", exc_info=True)


async def _send_call_notification(company_id, call_data: dict):
    """Background task: send Telegram notification for call events."""
    from utils.services.telegram_service import TelegramService

    state = call_data.get('state')
    if not state:
        return

    # Only notify on final call states
    is_answered = state == CallStatusEnum.ANSWER or (isinstance(state, str) and state == "ANSWER")
    is_missed = state in (CallStatusEnum.NOANSWER, CallStatusEnum.BUSY, CallStatusEnum.CANCEL) or (
        isinstance(state, str) and state in ("NOANSWER", "BUSY", "CANCEL")
    )

    if not is_answered and not is_missed:
        return

    try:
        # Use a fresh session for the background task
        async for session in AsyncDatabaseSession()():
            # Look up contact and operator names
            caller_phone = call_data.get('phone_1', '')
            contact_name = None
            contact_id = None
            operator_name = None
            direction = "inbound"

            if call_data.get('direction'):
                d = call_data['direction']
                direction = d.value if hasattr(d, 'value') else str(d)

            # Find matching contact by phone
            if caller_phone:
                from sqlalchemy import select, or_
                result = await session.execute(
                    select(Contact).where(
                        Contact.company_id == company_id,
                        or_(
                            Contact.phone == caller_phone,
                        )
                    ).limit(1)
                )
                contact = result.scalar_one_or_none()
                if contact:
                    contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()
                    contact_id = contact.id

            # Get operator name
            if call_data.get('operator_id'):
                operator = await User.get(session=session, id=call_data['operator_id'])
                if operator:
                    operator_name = operator.full_name

            if is_answered:
                await TelegramService.notify_call_completed(
                    session=session,
                    company_id=company_id,
                    caller_phone=caller_phone,
                    operator_name=operator_name,
                    duration_sec=call_data.get('billing_sec', 0) or 0,
                    contact_name=contact_name,
                    contact_id=contact_id,
                    record_url=call_data.get('record_url'),
                    direction=direction,
                )
            elif is_missed:
                await TelegramService.notify_call_missed(
                    session=session,
                    company_id=company_id,
                    caller_phone=caller_phone,
                    operator_name=operator_name,
                    contact_name=contact_name,
                    contact_id=contact_id,
                )
    except Exception as e:
        logger.error(f"Telegram call notification failed: {e}", exc_info=True)
