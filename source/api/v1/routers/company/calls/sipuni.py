"""
Sipuni-specific call endpoints

All endpoints validate that the company's provider is Sipuni.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.enums import ProviderEnum
from api.v1.schemas.call import (
    CallRequest, CallNumberRequest, CallTreeRequest, CallResponse,
)
from utils.services.telephony import ProviderFactory
from utils.services.telephony.base import ProviderException
from utils.permissions import require_permissions, Permissions

from .common import resolve_operator_id, require_provider, next_call_number


router = APIRouter(prefix="/calls/sipuni", tags=["Calls - Sipuni"])

_sipuni_company = require_provider(ProviderEnum.SIPUNI)


@router.post("/external", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_external(
    request: CallRequest,
    company: Company = Depends(_sipuni_company),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call from external number to external number

    Sipuni /api/callback/call_external — connects two external phones
    through the operator's SIP extension.
    """
    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
            request.operator_id, company.id, session
        ) if request.operator_id else None
        db_operator_id = resolved_operator_id or user.id

        result = await provider.make_call(request)

        if result.success:
            call_num = await next_call_number(session, company.id)
            await CallEvent.create(
                session=session,
                company_id=company.id,
                id=call_num,
                provider_type=company.provider_type,
                provider_call_id=f"sipuni_{result.call_id}",
                phone_1=request.phone_1,
                phone_2=request.phone_2,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sipuni service error")


@router.post("/number", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_number(
    request: CallNumberRequest,
    company: Company = Depends(_sipuni_company),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call from internal SIP extension to external phone number

    Sipuni /api/callback/call_number — the operator's SIP phone rings first
    (or the external number, if reverse=True).
    """
    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
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
            call_num = await next_call_number(session, company.id)
            await CallEvent.create(
                session=session,
                company_id=company.id,
                id=call_num,
                provider_type=company.provider_type,
                provider_call_id=f"sipuni_{result.call_id}",
                phone_1=request.operator_id,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sipuni service error")


@router.post("/tree", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_tree(
    request: CallTreeRequest,
    company: Company = Depends(_sipuni_company),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call external number through a call tree/scheme (IVR)

    Sipuni /api/callback/call_tree — routes the call through a configured
    call tree (scheme) before connecting.
    """
    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
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
            call_num = await next_call_number(session, company.id)
            await CallEvent.create(
                session=session,
                company_id=company.id,
                id=call_num,
                provider_type=company.provider_type,
                provider_call_id=f"sipuni_{result.call_id}",
                phone_1=request.operator_id,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
                attempts=1
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sipuni service error")


@router.post("/{call_id}/cancel", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def cancel_call(
    call_id: int,
    company: Company = Depends(_sipuni_company),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Cancel an active callback call

    Accepts the company-scoped call number. Resolves the provider call ID
    internally and calls Sipuni /api/callback/cancel.
    """
    call_event = await CallEvent.get(
        session=session,
        company_id=company.id,
        id=call_id,
    )
    if not call_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found"
        )

    raw_provider_id = call_event.provider_call_id.removeprefix("sipuni_")

    try:
        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        result = await provider.cancel_call(raw_provider_id)
        return CallResponse(
            success=result.success,
            call_id=call_id,
            message=result.message,
            error=result.error,
        )

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Sipuni service error")
