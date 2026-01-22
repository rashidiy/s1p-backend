"""
Unified call management endpoints (provider-agnostic)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from uuid import UUID

from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from api.v1.schemas.call import CallRequest, CallResponse, CallEventResponse, CallRecordingURL
from utils.services.telephony import ProviderFactory
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.post("/", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def make_call(
    request: CallRequest,
    user: User = Depends(User.current)
):
    """
    Make a call (provider-agnostic)

    Automatically routes to the correct provider (Sipuni or Binotel)
    based on the company's configuration.
    """
    # Get user's company
    company = await Company.get_or_404(id=user.company_id)

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


@router.get("/", response_model=List[CallEventResponse])
@require_permissions(Permissions.CALLS_READ)
async def list_calls(
    skip: int = 0,
    limit: int = 100,
    user: User = Depends(User.current)
):
    """List all calls for the company"""
    calls = await CallEvent.get_all(
        company_id=user.company_id,
        skip=skip,
        limit=limit,
        order_by=CallEvent.created_at.desc()
    )
    return calls


@router.get("/{call_id}", response_model=CallEventResponse)
@require_permissions(Permissions.CALLS_READ)
async def get_call(
    call_id: UUID,
    user: User = Depends(User.current)
):
    """Get call details"""
    call = await CallEvent.get_or_404(
        id=call_id,
        company_id=user.company_id
    )
    return call


@router.get("/{call_id}/recording", response_model=CallRecordingURL)
@require_permissions(Permissions.CALLS_READ)
async def get_call_recording(
    call_id: UUID,
    user: User = Depends(User.current)
):
    """
    Get proxied call recording URL

    Returns a secure, time-limited URL to access the call recording.
    """
    call = await CallEvent.get_or_404(
        id=call_id,
        company_id=user.company_id
    )

    if not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording available for this call"
        )

    # TODO: Generate signed token for proxied URL
    # For now, return the direct URL
    return CallRecordingURL(
        url=call.record_url,
        expires_in=86400  # 24 hours
    )
