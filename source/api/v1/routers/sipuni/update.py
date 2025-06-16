from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import SipuniSchema
from db import get_session
from db.models import User, Sipuni
from . import router


@router.post('/regenerate_token')
async def regenerate_sipuni_token(
        id_: int = Query(..., alias='id'),
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    cabinet_id = await Sipuni.get_or_404(fields=(Sipuni.cabinet_id,), id=id_, user_id=user.id, session=session)
    token = Sipuni.generate_token(cabinet_id)
    await Sipuni.update_by(id=id_, values={'token': token}, session=session)
    return {'token': token}


@router.patch('/update', response_model=SipuniSchema.SipuniResponse)
async def update_sipuni(
        data: SipuniSchema.SipuniUpdateRequest,
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    sipuni = await Sipuni.get_or_404(id=data.id, user_id=user.id, session=session)
    if data.company_name: sipuni.company_name = data.company_name
    if data.cabinet_id: sipuni.cabinet_id = data.cabinet_id
    if data.security_key: sipuni.security_key = data.security_key
    if data.partner_name: sipuni.partner_name = data.partner_name
    if data.partner_contact: sipuni.partner_contact = data.partner_contact
    if data.comment: sipuni.comment = data.comment

    await sipuni.update(session=session)
    return sipuni
