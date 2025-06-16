from typing import List

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import SipuniSchema
from db import get_session
from db.models import User, Sipuni
from . import router


@router.get('/list', response_model=List[SipuniSchema.SipuniResponse])
async def get_sipuni_list(
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    sipuni_objects = await Sipuni.get_all(user_id=user.id, session=session)
    return sipuni_objects


@router.get('/detail', response_model=SipuniSchema.SipuniResponse)
async def get_sipuni_detail(
        id_: int = Query(..., alias='id'),
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    sipuni = await Sipuni.get_or_404(id=id_, user_id=user.id, session=session)
    return sipuni
