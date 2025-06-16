from typing import List

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import Response

from api.v1.schemas import SipuniSchema
from db import get_session
from db.models import User, Sipuni
from . import router


@router.post('/create', response_model=SipuniSchema.SipuniResponse)
async def create_sipuni(
        data: SipuniSchema.SipuniCreateRequest,
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    exists = await Sipuni.exists(user_id=user.id, cabinet_id=data.cabinet_id, session=session)
    if exists: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Sipuni cabinet already exists')

    sipuni = await Sipuni.create(
        **data.model_dump(), user_id=user.id, token=Sipuni.generate_token(data.cabinet_id), session=session
    )
    return sipuni

