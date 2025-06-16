from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import Response

from db import get_session
from db.models import User, Sipuni
from . import router


@router.delete('/delete')
async def delete_sipuni(
        id_: int = Query(..., alias='id'),
        user: User = User.current(check_for_active=False),
        session: AsyncSession = Depends(get_session)
):
    deleted = await Sipuni.delete_by(id=id_, user_id=user.id, session=session)
    if not deleted: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Sipuni not found')
    return Response(status_code=status.HTTP_204_NO_CONTENT)
