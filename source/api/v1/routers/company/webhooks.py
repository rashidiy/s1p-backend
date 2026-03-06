"""
Unified webhook handler for all telephony providers
"""

import logging
from uuid import UUID
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import WebhookConfig
from db import get_session
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.user import User
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.enums import ProviderEnum
from utils.services.telephony import ProviderFactory
from api.v1.routers.company.calls.common import next_call_number

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


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
                detail=f"operator_id {operator_id} does not belong to this company",
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
                detail=f"contact_id {contact_id} does not belong to this company",
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
                detail=f"lead_id {lead_id} does not belong to this company",
            )


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

        # Validate normalized data against strict schema (extra='forbid')
        try:
            validated = WebhookCallData(**call_data)
        except Exception as e:
            logger.warning(
                f"Webhook payload validation failed for company {company.id}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid webhook payload: {str(e)}",
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

    except HTTPException:
        raise
    except Exception as e:
        # Log the error but return 200 to prevent provider retries
        logger.error(f"Webhook processing error for company {company.id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": "Internal processing error"}
