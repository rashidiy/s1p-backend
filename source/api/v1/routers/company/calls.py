"""
Unified call management endpoints (provider-agnostic)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from api.v1.schemas.call import CallRequest, CallResponse, CallEventResponse, CallRecordingURL
from utils.services.telephony import ProviderFactory
from utils.permissions import require_permissions, Permissions
from utils.managers import RecordTokenManager
from core.config import WebhookConfig, AppConfig

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post("", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def make_call(
    request: CallRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Make a call (provider-agnostic)

    Automatically routes to the correct provider (Sipuni or Binotel)
    based on the company's configuration.
    """
    # Get user's company
    company = await Company.get_or_404(id=user.company_id, session=session)

    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company is not active"
        )

    try:
        # Create provider instance (automatic routing!)
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        # Make call (same code for all providers)
        result = await provider.make_call(request)

        # Store call event if successful
        if result.success:
            await CallEvent.create(
                session=session,
                company_id=company.id,
                provider_type=company.provider_type,
                provider_call_id=result.call_id,
                phone_1=request.phone_1,
                phone_2=request.phone_2,
                operator_id=request.operator_id or user.id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to make call: {str(e)}"
        )


@router.get("", response_model=List[CallEventResponse])
@require_permissions(Permissions.CALLS_READ)
async def list_calls(
    skip: int = 0,
    limit: int = 100,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """List all calls for the company"""
    calls = await CallEvent.get_all(
        session=session,
        company_id=user.company_id,
        offset=skip,
        limit=limit,
        order_by=(CallEvent.created_at.desc(),)
    )
    return calls


@router.get("/{call_id}", response_model=CallEventResponse)
@require_permissions(Permissions.CALLS_READ)
async def get_call(
    call_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Get call details"""
    call = await CallEvent.get_or_404(
        session=session,
        id=call_id,
        company_id=user.company_id
    )
    return call


@router.get("/{call_id}/recording", response_model=CallRecordingURL)
@require_permissions(Permissions.CALLS_READ)
async def get_call_recording(
    call_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Get proxied call recording URL

    Returns a secure, time-limited URL to access the call recording.
    The URL is signed and expires after the configured time period.
    """
    call = await CallEvent.get_or_404(
        session=session,
        id=call_id,
        company_id=user.company_id
    )

    if not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording available for this call"
        )

    # Generate signed token for proxied access
    if WebhookConfig.RECORD_PROXY_SECRET:
        # Use proxied URL with signed token
        proxied_url = RecordTokenManager.generate_proxied_url(
            call_id=call.id,
            company_id=user.company_id,
            base_url=AppConfig.BASE_URL
        )
        return CallRecordingURL(
            url=proxied_url,
            expires_in=WebhookConfig.RECORD_PROXY_TOKEN_EXPIRY
        )
    else:
        # Fallback: return direct URL (less secure, for development)
        return CallRecordingURL(
            url=call.record_url,
            expires_in=86400  # 24 hours
        )
