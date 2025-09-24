import asyncio
from datetime import datetime

from fastapi.params import Query
from sqlalchemy import select, func, text

from api.v1.routers import router
from api.v1.schemas.sipuni import StatisticsSchema
from db.base import AsyncDatabaseSession
from db.models.enums import CallStatusEnum
from db.models.sipuni import CallEvent


@router.get('/statistics/general')
async def get_statistics(
        represent: StatisticsSchema.RepresentEnum = Query(StatisticsSchema.RepresentEnum.daily),
        start: datetime = Query(datetime.today().replace(hour=0, minute=0, second=0).isoformat(timespec='seconds')),
        end: datetime = Query(datetime.today().replace(hour=23, minute=59, second=59).isoformat(timespec='seconds')),
):
    return {
        "summary": {
            "total_calls": 110,
            "answered_calls": 68,
            "internal_calls": 55,
            "external_calls": 67,
            "top_performing_operator": "201",
            "average_call_duration": 78
        },
        "data": [
            {
                "timestamp": "2025-12-03T00:00:00+05:00",
                "label": "Monday",
                "total_calls": 98,
                "answered_calls": 77,
                "external_calls": 33,
                "internal_calls": 44,
                "top_performing_operator": "201"
            },
            {
                "timestamp": "2025-12-03T00:00:00+05:00",
                "label": "Tuesday",
                "total_calls": 98,
                "answered_calls": 77,
                "external_calls": 33,
                "internal_calls": 44,
                "top_performing_operator": "201"
            }
        ]
    }


async def main():
    start = datetime.strptime("2025-07-01T00:00:00", "%Y-%m-%dT%H:%M:%S")
    end = datetime.strptime("2025-09-30T00:00:00", "%Y-%m-%dT%H:%M:%S")

    async with AsyncDatabaseSession._session_factory() as session:
        stmt = (
            select(
                func.count().label("all"),
                func.count().filter(CallEvent.status == CallStatusEnum.ANSWER).label("accepted"),
                func.date_trunc(text("'day'"), CallEvent.created_at).label('datetime')
            )
            .group_by(func.date_trunc(text("'day'"), CallEvent.created_at))
            .where(CallEvent.created_at >= start, CallEvent.created_at <= end)
        )
        query = await session.execute(stmt)
        results = query.all()

    for row in results:
        print(dict(row._mapping))


if __name__ == '__main__':
    asyncio.run(main())
