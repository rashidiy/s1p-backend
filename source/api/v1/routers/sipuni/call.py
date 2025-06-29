from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas.sipuni import CallSchema
from db import get_session
from db.models import Sipuni
from utils.services import SipuniApiSimulator
from . import router


@router.post("/internal_call", tags=["Call"])
async def call_number(data: CallSchema.CallNumberRequest, session: AsyncSession = Depends(get_session)):
    company = await Sipuni.get_or_404(token=data.token, session=session)
    response = await SipuniApiSimulator.call_number(
        user=company.cabinet_id,
        secret=company.security_key,
        phone=data.phone,
        sipnumber=data.sip_number,
        reverse=data.reverse,
        antiaon=data.antiaon,
    )
    return response.json()


@router.post("/external_call", tags=["Call"])
async def external_call(data: CallSchema.ExternalCallRequest, session: AsyncSession = Depends(get_session)):
    company = await Sipuni.get_or_404(token=data.token, session=session)
    response = await SipuniApiSimulator.external_call(
        user=company.cabinet_id,
        secret=company.security_key,
        phone_from=data.phone1,
        phone_to=data.phone2,
        sipnumber=data.bridge_start,
        sipnumber2=data.bridge_end
    )
    return response.json()


@router.post("/call_tree", tags=["Call"])
async def external_call(data: CallSchema.CallTreeRequest, session: AsyncSession = Depends(get_session)):
    company = await Sipuni.get_or_404(token=data.token, session=session)
    response = await SipuniApiSimulator.call_tree(
        user=company.cabinet_id,
        secret=company.security_key,
        phone=data.phone,
        sipnumber=data.sip_number,
        tree=data.tree,
        reverse=data.reverse,
        attempt_duration=data.attempt_duration
    )
    return response.json()
