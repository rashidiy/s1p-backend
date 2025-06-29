import string
from random import choice

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import SipuniSchema
from db import get_session
from db.models import User, Sipuni
from . import router


def generate_token(cabinet_id):
    filler = ''.join([choice(string.ascii_letters + string.digits) for _ in range(63 - len(cabinet_id))])
    return f'{cabinet_id}:{filler}'


@router.post('/create', response_model=SipuniSchema.SipuniResponse)
async def create_sipuni(
        data: SipuniSchema.SipuniCreateRequest,
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    exists = await Sipuni.exists(user_id=user.id, cabinet_id=data.cabinet_id, session=session)
    if exists: raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Sipuni cabinet already exists')

    sipuni = await Sipuni.create(
        **data.model_dump(), user_id=user.id, token=generate_token(data.cabinet_id), session=session
    )
    return sipuni
