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
from sqlalchemy.exc import IntegrityError
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
from api.v1.routers.company.calls.common import resolve_operator_id

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

    # Cache scalar values — ORM objects expire after session.rollback()
    company_id = company.id
    provider_type = company.provider_type
    provider_config = company.provider_config

    # Validate source IP against provider whitelist
    if not validate_webhook_ip(request, provider_type):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: IP not whitelisted for this provider"
        )

    try:
        # Create provider instance
        provider = ProviderFactory.create(
            provider_type=provider_type.value,
            config=provider_config
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
                f"Webhook payload validation failed for company {company_id}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid webhook payload",
            )

        # Convert to dict, excluding None values and fields we'll set manually
        call_data = validated.model_dump(exclude_none=True)

        # Add company_id to call data
        call_data['company_id'] = company_id
        call_data['provider_type'] = provider_type

        # Validate entity ownership before creating/updating
        await _validate_entity_ownership(
            session=session,
            company_id=company_id,
            operator_id=call_data.get('operator_id'),
            contact_id=call_data.get('contact_id'),
            lead_id=call_data.get('lead_id'),
        )

        # Resolve operator from last_called SIP extension (for inbound calls)
        if not call_data.get('operator_id') and call_data.get('last_called'):
            last_ext = call_data['last_called'].split(',')[-1].strip()
            if last_ext:
                resolved = await resolve_operator_id(last_ext, company_id, session)
                if resolved:
                    call_data['operator_id'] = resolved

        # Flag inbound missed calls for callback
        state = call_data.get('state')
        direction = call_data.get('direction')
        if direction == 'inbound' and state in ('NOANSWER', 'BUSY', 'CANCEL'):
            call_data['needs_callback'] = True

        # Auto-resolve callback: outbound call to a number that has pending missed calls
        if direction == 'outbound' and event_type == 'call_ended' and state == 'ANSWER':
            outbound_dest = call_data.get('phone_2') or call_data.get('phone_1')
            if outbound_dest:
                from sqlalchemy import update, and_
                from sqlalchemy.sql import func as sql_func
                await session.execute(
                    update(CallEvent).where(
                        and_(
                            CallEvent.company_id == company_id,
                            CallEvent.direction == 'inbound',
                            CallEvent.needs_callback == True,
                            CallEvent.phone_1 == outbound_dest,
                        )
                    ).values(needs_callback=False, callback_at=sql_func.now())
                )

        # Check if call event already exists (for updates)
        existing_call = await CallEvent.get(
            session=session,
            company_id=company_id,
            provider_type=provider_type,
            provider_call_id=call_data['provider_call_id']
        )

        if existing_call:
            return await _update_existing_call(
                session, background_tasks, company_id, existing_call, call_data, event_type,
            )
        else:
            # Let PostgreSQL sequence auto-generate the id
            try:
                call_event = await CallEvent.create(session=session, **call_data)
            except IntegrityError:
                # Race condition: another concurrent webhook for the same call
                # inserted first (unique constraint on company+provider+call_id).
                # Rollback the failed INSERT, re-fetch, and update instead.
                await session.rollback()
                existing_call = await CallEvent.get(
                    session=session,
                    company_id=company_id,
                    provider_type=provider_type,
                    provider_call_id=call_data['provider_call_id']
                )
                if existing_call:
                    return await _update_existing_call(
                        session, background_tasks, company_id, existing_call, call_data, event_type,
                    )
                # If still not found, re-raise — something unexpected happened
                raise

            # Fire notifications based on event type
            _schedule_notifications(
                background_tasks, session, company_id,
                call_data, call_event.id, event_type,
            )
            return {"status": "created", "call_id": call_event.id}

    except HTTPException:
        raise
    except Exception as e:
        # Log the error but return 200 to prevent provider retries
        logger.error(f"Webhook processing error for company {company_id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Internal processing error"}


async def _update_existing_call(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    company_id: UUID,
    existing_call: CallEvent,
    call_data: dict,
    event_type: Optional[str],
):
    """Update an existing call event with new webhook data."""
    # Cache scalar values before any DB ops that might expire the object
    existing_call_id = existing_call.id
    existing_phone_1 = existing_call.phone_1
    existing_phone_2 = existing_call.phone_2
    existing_state = existing_call.state

    # Skip duplicate Event 1 (SIP calls fire 2x Event 1, 1s apart)
    if event_type == "call_started" and existing_state == CallStatusEnum.RINGING:
        return {"status": "duplicate", "call_id": existing_call_id}

    # Don't overwrite phones set by call endpoint with SIP extensions from webhook
    if existing_phone_1 and 'phone_1' in call_data:
        call_data.pop('phone_1')
    if existing_phone_2 and 'phone_2' in call_data:
        call_data.pop('phone_2')

    # Guard: don't let earlier events overwrite terminal states with RINGING
    incoming_state = call_data.get('state')
    if (
        existing_state in _TERMINAL_STATES
        and incoming_state
        and incoming_state == CallStatusEnum.RINGING.value
    ):
        call_data.pop('state', None)

    # Guard: don't overwrite a valid answer timestamp (from event 3) with
    # a broken one from event 2 (external calls have answer <= start)
    existing_answer_ts = existing_call.call_answer_timestamp
    incoming_answer_ts = call_data.get('call_answer_timestamp')
    if existing_answer_ts and incoming_answer_ts is None:
        # Event 2 had broken timestamp (stripped by provider), keep event 3's value
        call_data.pop('call_answer_timestamp', None)
        # Recompute billing_sec using the existing valid answer timestamp
        end_ts = call_data.get('call_end_timestamp')
        if call_data.get('state') == 'ANSWER' and end_ts and existing_answer_ts:
            call_data['billing_sec'] = max(0, end_ts - existing_answer_ts)

    # Update existing call event (company_id for defense-in-depth)
    await CallEvent.update_by(
        session=session,
        values=call_data,
        id=existing_call_id,
        company_id=company_id,
    )

    # Fire notifications based on event type
    _schedule_notifications(
        background_tasks, session, company_id,
        call_data, existing_call_id, event_type,
    )
    return {"status": "updated", "call_id": existing_call_id}


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
            _send_call_notification, company_id, call_data, call_id
        )
        background_tasks.add_task(
            _fire_call_webhook, session, company_id, call_data, call_id,
        )

    else:
        # Legacy path (Binotel or unknown) — keep existing behavior
        background_tasks.add_task(
            _send_call_notification, company_id, call_data, call_id
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


async def _send_call_notification(company_id, call_data: dict, call_id: int = None):
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
        async for session in AsyncDatabaseSession()():
            if not call_id:
                return
            call_event = await CallEvent.get(session=session, id=call_id, company_id=company_id)
            if not call_event:
                return

            if is_answered:
                await TelegramService.send_call_notification(
                    company_id=company_id,
                    call_event=call_event,
                    session=session,
                )
            elif is_missed:
                await TelegramService.send_missed_call_notification(
                    company_id=company_id,
                    call_event=call_event,
                    session=session,
                )
    except Exception as e:
        logger.error(f"Telegram call notification failed: {e}", exc_info=True)
