import uuid
from datetime import datetime, tzinfo, timezone, timedelta

from fastapi import Depends
from fastapi.params import Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.routers import router
from api.v1.schemas.sipuni.statistics import RepresentEnum
from api.v1.services.sipuni.statistics import get_call_statistics
from db import get_session

UTC_PLUS_5 = timezone(timedelta(hours=5))


@router.get("/statistics/calls")  # , response_model=CallStatsResponse
async def call_statistics(
        sipuni_id: uuid.UUID,
        represent: RepresentEnum = Query(RepresentEnum.day),
        start: datetime = Query(datetime.now(UTC_PLUS_5).replace(hour=0, minute=0, second=0)),
        end: datetime = Query(datetime.now(UTC_PLUS_5).replace(hour=23, minute=59, second=59)),
        session: AsyncSession = Depends(get_session),
):
    return await get_call_statistics(
        sipuni_id=sipuni_id,
        represent=represent,
        time_start=start,
        time_end=end,
        session=session
    )
