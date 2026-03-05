import enum
from datetime import datetime

from pydantic import BaseModel


class RepresentEnum(enum.Enum):
    day = "day"
    weekly = "week"
    monthly = "month"
    yearly = "year"


class CallSummary(BaseModel):
    all: int
    accepted: int
    internal: int
    external: int
    top_operator: str | None
    avg_duration: float


class CallStatItem(BaseModel):
    label: str
    time_start: datetime
    time_end: datetime
    all: int
    accepted: int
    internal: int
    external: int
    top_operator: str | None
    avg_duration: float | None


class CallStatsResponse(BaseModel):
    calls: CallSummary
    data: list[CallStatItem]
