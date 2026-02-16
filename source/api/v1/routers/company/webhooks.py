"""
Unified webhook handler for all telephony providers
"""

import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.config import WebhookConfig
from db import get_session
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.enums import ProviderEnum
from utils.services.telephony import ProviderFactory
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
            return {"status": "updated", "call_id": existing_call.id}
        else:
            # Assign company-scoped id for new events
            call_data['id'] = await next_call_number(session, company.id)
            call_event = await CallEvent.create(session=session, **call_data)
            return {"status": "created", "call_id": call_event.id}

    except Exception as e:
        # Log the error but return 200 to prevent provider retries
        logger.error(f"Webhook processing error for company {company.id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
