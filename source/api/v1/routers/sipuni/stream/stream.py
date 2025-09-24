import os
import uuid

from fastapi import Path, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.requests import Request

from api.v1.routers.sipuni import router
from api.v1.schemas import SipuniEventSchema as SESch
from db import get_session
from db.models.sipuni import CallEvent, Sipuni
from .broadcast import Broadcast


async def ip_address_checkup(request: Request):
    allowed_ips = set(os.getenv('ALLOWED_IPS').split(';'))
    client_ip = request.client.host
    if client_ip not in allowed_ips:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden IP")


@router.get('/stream/{id}/', tags=['Streams'])
async def stream(
        request: Request,
        id_: uuid.UUID = Path(alias='id'),
        session: AsyncSession = Depends(get_session),
        _=Depends(ip_address_checkup)):
    sipuni = await Sipuni.get_or_404(id=id_, session=session)
    try:
        query_params = request.query_params
        if (event := query_params.get('event')) and event == '2':
            hangup_event = SESch.HangupEvent(**request.query_params)
            # await Broadcast(sipuni, hangup_event).broadcast()
            await CallEvent.create(**hangup_event.model_dump(), sipuni_id=id_, session=session)
    except Exception as e:
        print(e)
    return {"success": True}
