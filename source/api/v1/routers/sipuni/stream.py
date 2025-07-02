import os
import uuid

from fastapi import Path, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.requests import Request

from api.v1.schemas import SipuniEventSchema as SESch
from db import get_session
from db.models.enums import CallStatusEnum
from db.models.sipuni import CallEvent
from . import router


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
    try:
        query_params = request.query_params
        if (event := query_params.get('event')) and event == '2':
            hangup_event = SESch.HangupEvent(**request.query_params)
            await broadcast(hangup_event)
            await CallEvent.create(**hangup_event.model_dump(), sipuni_id=id_, session=session)
    except Exception as e:
        print(e)
    return {"success": True}


async def broadcast(event: SESch.HangupEvent, lang: str = 'en'):
    status_messages = {
        ('1', '2', CallStatusEnum.ANSWER): 'Subscriber answered',
        ('1', '2', CallStatusEnum.NOANSWER): 'Subscriber not answered',
    }
    print(
        status_messages.get(
            (event.dst_type, event.src_type, event.status),
            (event.dst_type, event.src_type, event.status)
        )
    )
