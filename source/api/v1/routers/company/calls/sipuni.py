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
from db.models.enums import ProviderEnum, RoleEnum
from api.v1.schemas.call import (
    CallRequest, CallNumberRequest, CallTreeRequest, CallResponse,
)
from utils.services.telephony import ProviderFactory
from utils.services.telephony.base import ProviderException
from utils.permissions import require_permissions, Permissions

from .common import resolve_operator_id, require_provider, next_call_number


def _resolve_sip_ext(user: User, request_operator_id: str | None) -> str:
    """Determine the SIP extension to use for the call.

    Operators always use their assigned extension.
    Admins/managers use the one they provide in the request.
    """
    if user.role == RoleEnum.COMPANY_OPERATOR:
        if not user.sip_extension:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No SIP extension assigned to your account",
            )
        return user.sip_extension
    if request_operator_id:
        return request_operator_id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Operator SIP extension is required",
    )


router = APIRouter(prefix="/calls/sipuni", tags=["Calls - Sipuni"])


async def _upsert_call_event(
    session: AsyncSession,
    company: Company,
    provider_call_id: str,
    phone_1: str,
    phone_2: str,
    operator_id,
    utm_source=None,
    utm_medium=None,
    utm_campaign=None,
) -> int:
    """Create or update a CallEvent, handling the race with webhook event 1.

    When a call is initiated, Sipuni may fire event 1 (call start) before
    this endpoint finishes. If the webhook already created the row, we
    update it with operator_id and UTM data instead of failing with a
    duplicate key error.
    """
    existing = await CallEvent.get(
        session=session,
        company_id=company.id,
        provider_type=company.provider_type,
        provider_call_id=provider_call_id,
    )
    if existing:
        await CallEvent.update_by(
            session=session,
            values={
                "operator_id": operator_id,
                "phone_1": phone_1,
                "phone_2": phone_2,
                "utm_source": utm_source,
                "utm_medium": utm_medium,
                "utm_campaign": utm_campaign,
            },
            id=existing.id,
            company_id=company.id,
        )
        return existing.id
    else:
        call_num = await next_call_number(session, company.id)
        await CallEvent.create(
            session=session,
            company_id=company.id,
            id=call_num,
            provider_type=company.provider_type,
            provider_call_id=provider_call_id,
            phone_1=phone_1,
            phone_2=phone_2,
            operator_id=operator_id,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            attempts=1,
        )
        return call_num

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
        sip_ext = _resolve_sip_ext(user, request.operator_id)

        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
            sip_ext, company.id, session
        )
        db_operator_id = resolved_operator_id or user.id

        # Override operator_id with resolved SIP extension for the provider call
        request.operator_id = sip_ext
        result = await provider.make_call(request)

        if result.success:
            provider_call_id = f"sipuni_{result.call_id}"
            call_num = await _upsert_call_event(
                session=session,
                company=company,
                provider_call_id=provider_call_id,
                phone_1=request.phone_1,
                phone_2=request.phone_2,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sipuni service error: {e}")


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
        sip_ext = _resolve_sip_ext(user, request.operator_id)

        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
            sip_ext, company.id, session
        )
        db_operator_id = resolved_operator_id or user.id

        result = await provider.call_number(
            phone=request.phone,
            sipnumber=sip_ext,
            reverse=request.reverse,
            antiaon=request.antiaon,
        )

        if result.success:
            provider_call_id = f"sipuni_{result.call_id}"
            call_num = await _upsert_call_event(
                session=session,
                company=company,
                provider_call_id=provider_call_id,
                phone_1=sip_ext,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sipuni service error: {e}")


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
        sip_ext = _resolve_sip_ext(user, request.operator_id)

        provider = ProviderFactory.create(
            provider_type=company.provider_type.value,
            config=company.provider_config
        )

        resolved_operator_id = await resolve_operator_id(
            sip_ext, company.id, session
        )
        db_operator_id = resolved_operator_id or user.id

        result = await provider.call_tree(
            phone=request.phone,
            sipnumber=sip_ext,
            tree=request.tree,
            reverse=request.reverse,
            call_attempt_time=request.call_attempt_time,
        )

        if result.success:
            provider_call_id = f"sipuni_{result.call_id}"
            call_num = await _upsert_call_event(
                session=session,
                company=company,
                provider_call_id=provider_call_id,
                phone_1=sip_ext,
                phone_2=request.phone,
                operator_id=db_operator_id,
                utm_source=request.utm_source,
                utm_medium=request.utm_medium,
                utm_campaign=request.utm_campaign,
            )
            return CallResponse(success=True, call_id=call_num)

        return CallResponse(success=False, error=result.error, message=result.message)

    except ProviderException as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sipuni service error: {e}")


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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sipuni service error: {e}")


# ── Sipuni Operators List ─────────────────────────────────────────────

# In-memory cache: {company_id: {"data": [...], "expires": timestamp}}
_operators_cache: dict = {}
_CACHE_TTL = 600  # 10 minutes


@router.get("/operators")
@require_permissions(Permissions.CALLS_MAKE)
async def list_sipuni_operators(
    company: Company = Depends(_sipuni_company),
    user: User = User.current(),
):
    """
    List all Sipuni operators (SIP extensions) with their online status.

    Calls Sipuni statistic/operators API and parses the CSV response.
    Results are cached for 10 minutes per company.
    """
    import hashlib
    import csv
    import io
    import time
    import httpx

    # Check cache
    cache_key = str(company.id)
    cached = _operators_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return cached["data"]

    cabinet_id = (company.provider_config or {}).get("cabinet_id")
    security_key = (company.provider_config or {}).get("security_key")

    if not cabinet_id or not security_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sipuni credentials not configured",
        )

    hash_value = hashlib.md5(
        f"{cabinet_id}+{security_key}".encode()
    ).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://sipuni.com/api/statistic/operators",
                data={"user": cabinet_id, "hash": hash_value},
            )
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Sipuni service error: {e}",
        )

    # Parse CSV response: extension;name;status (first row is header)
    text = resp.text.strip()
    if not text:
        return []

    operators = []
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header_skipped = False
    for row in reader:
        if not header_skipped:
            header_skipped = True
            continue
        if len(row) >= 2:
            operators.append({
                "extension": row[0].strip(),
                "name": row[1].strip() if len(row) > 1 else "",
                "status": row[2].strip() if len(row) > 2 else "unknown",
            })

    # Cache result
    _operators_cache[cache_key] = {"data": operators, "expires": time.time() + _CACHE_TTL}

    return operators
