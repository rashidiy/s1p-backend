"""
Unified call management endpoints (provider-agnostic)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from api.v1.schemas.call import (
    CallRequest, CallNumberRequest, CallTreeRequest,
    CallResponse, CallEventResponse, CallRecordingURL,
)
from utils.services.telephony import ProviderFactory
from utils.services.telephony.base import ProviderException
from utils.permissions import require_permissions, Permissions
from utils.managers import RecordTokenManager
from core.config import WebhookConfig, AppConfig


async def _resolve_operator_id(
    operator_id: Optional[str],
    company_id: UUID,
    session: AsyncSession,
) -> Optional[UUID]:
    """Resolve operator_id string to a user UUID.

    Accepts UUID, phone, or email. Returns None if not found.
    """
    if not operator_id:
        return None

    # Try UUID first
    try:
        uid = UUID(operator_id)
        user = await User.get(id=uid, company_id=company_id, session=session)
        if user:
            return user.id
    except ValueError:
        pass

    # Try phone
    user = await User.get(phone=operator_id, company_id=company_id, session=session)
    if user:
        return user.id

    # Try email
    user = await User.get(email=operator_id, company_id=company_id, session=session)
    if user:
        return user.id

    # Not found as a user — may be a raw SIP extension; let it pass through
    return None


async def _get_active_company(user: User, session: AsyncSession) -> Company:
    """Get the user's company and verify it's active."""
    company = await Company.get_or_404(id=user.company_id, session=session)
    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company is not active"
        )
    return company


router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post("", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def make_call(
    request: CallRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call from external number to external number (provider-agnostic)

    Automatically routes to the correct provider (Sipuni or Binotel)
    based on the company's configuration.
    """
    company = await _get_active_company(user, session)

    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await _resolve_operator_id(
            request.operator_id, company.id, session
        ) if request.operator_id else None
        resolved_operator_id = resolved_operator_id or user.id

        result = await provider.make_call(request)

        if result.success:
            await CallEvent.create(
                session=session,
                company_id=company.id,
                provider_type=company.provider_type,
                provider_call_id=result.call_id,
                phone_1=request.phone_1,
                phone_2=request.phone_2,
                operator_id=resolved_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )

        return result

    except ProviderException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to make call: {str(e)}"
        )


@router.post("/number", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_number(
    request: CallNumberRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call from internal SIP extension to external phone number

    The operator_id is used as the SIP extension number
    (or resolved from UUID/phone/email).
    """
    company = await _get_active_company(user, session)

    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await _resolve_operator_id(
            request.operator_id, company.id, session
        )
        db_operator_id = resolved_operator_id or user.id

        result = await provider.call_number(
            phone=request.phone,
            sipnumber=request.operator_id,
            reverse=request.reverse,
            antiaon=request.antiaon,
        )

        if result.success:
            await CallEvent.create(
                session=session,
                company_id=company.id,
                provider_type=company.provider_type,
                provider_call_id=result.call_id,
                phone_1=request.operator_id,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )

        return result

    except ProviderException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to call number: {str(e)}"
        )


@router.post("/tree", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_tree(
    request: CallTreeRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call external number through a call tree/scheme (IVR)

    The operator_id is used as the SIP extension that initiates the call.
    """
    company = await _get_active_company(user, session)

    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await _resolve_operator_id(
            request.operator_id, company.id, session
        )
        db_operator_id = resolved_operator_id or user.id

        result = await provider.call_tree(
            phone=request.phone,
            sipnumber=request.operator_id,
            tree=request.tree,
            reverse=request.reverse,
            call_attempt_time=request.call_attempt_time,
        )

        if result.success:
            await CallEvent.create(
                session=session,
                company_id=company.id,
                provider_type=company.provider_type,
                provider_call_id=result.call_id,
                phone_1=request.operator_id,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )

        return result

    except ProviderException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to call tree: {str(e)}"
        )


@router.post("/{call_id}/cancel", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def cancel_call(
    call_id: str,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Cancel an active callback call

    Pass the provider call_id (callbackId) returned from a make call response.
    """
    company = await _get_active_company(user, session)

    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        result = await provider.cancel_call(call_id)
        return result

    except ProviderException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel call: {str(e)}"
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
