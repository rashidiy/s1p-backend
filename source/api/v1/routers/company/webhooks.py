"""
Unified webhook handler for all telephony providers
"""

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.config import WebhookConfig
from db import get_session
from db.base import AsyncDatabaseSession
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.contact import Contact
from db.models.user import User
from db.models.enums import ProviderEnum, CallStatusEnum
from utils.services.telephony import ProviderFactory
from utils.services.webhook import fire_webhook_event
from api.v1.routers.company.calls.common import next_call_number

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


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

    # Get client IP from request
    client_ip = request.client.host if request.client else None
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


@router.get("/{token}")
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

        # Add company_id to call data
        call_data['company_id'] = company.id
        call_data['provider_type'] = company.provider_type

        # Check if call event already exists (for updates)
        existing_call = await CallEvent.get(
            session=session,
            company_id=company.id,
            provider_type=company.provider_type,
            provider_call_id=call_data['provider_call_id']
        )

        if existing_call:
            # Update existing call event
            await CallEvent.update_by(
                session=session,
                values=call_data,
                id=existing_call.id
            )
            # Send Telegram notification for completed/missed calls on update
            background_tasks.add_task(
                _send_call_notification, company.id, call_data
            )
            # Fire outbound webhook for call events
            await _fire_call_webhook(session, company.id, call_data, existing_call.id)
            return {"status": "updated", "call_id": existing_call.id}
        else:
            # Assign company-scoped id for new events
            call_data['id'] = await next_call_number(session, company.id)
            call_event = await CallEvent.create(session=session, **call_data)
            # Send Telegram notification for completed/missed calls
            background_tasks.add_task(
                _send_call_notification, company.id, call_data
            )
            # Fire outbound webhook for call events
            await _fire_call_webhook(session, company.id, call_data, call_event.id)
            return {"status": "created", "call_id": call_event.id}

    except Exception as e:
        # Log the error but return 200 to prevent provider retries
        logger.error(f"Webhook processing error for company {company.id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Internal processing error"}


async def _fire_call_webhook(session, company_id, call_data: dict, call_id):
    """Fire outbound webhook for call.completed or call.missed events."""
    state = call_data.get('state')
    if not state:
        return

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
                "state": state.value if hasattr(state, 'value') else str(state),
            },
            session=session,
        )
    except Exception as e:
        logger.error(f"Outbound webhook fire failed for call event: {e}", exc_info=True)


async def _send_call_notification(company_id, call_data: dict):
    """Background task: send Telegram notification for call events."""
    from utils.services.telegram import TelegramService
    from sqlalchemy import or_

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
