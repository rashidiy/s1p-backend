"""
Binotel-specific call endpoints

All endpoints validate that the company's provider is Binotel.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.enums import ProviderEnum
from api.v1.schemas.call import CallRequest, CallResponse
from utils.services.telephony import ProviderFactory
from utils.services.telephony.base import ProviderException
from utils.permissions import require_permissions, Permissions

from .common import resolve_operator_id, require_provider, next_call_number


router = APIRouter(prefix="/calls/binotel", tags=["Calls - Binotel"])

_binotel_company = require_provider(ProviderEnum.BINOTEL)


@router.post("/ext-to-ext", response_model=CallResponse)
@require_permissions(Permissions.CALLS_MAKE)
async def call_ext_to_ext(
    request: CallRequest,
    company: Company = Depends(_binotel_company),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Call from external number to external number

    Binotel /api/4.0/calls/external-number-to-external-number.json
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
                provider_call_id=f"binotel_{result.call_id}",
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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
