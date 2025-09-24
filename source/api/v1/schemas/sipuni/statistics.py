import enum
from datetime import datetime

from pydantic import BaseModel


class StatisticsSchema:
    class RepresentEnum(enum.Enum):
        daily = "daily"
        weekly = "weekly"
        monthly = "monthly"
        yearly = "yearly"

    class GeneralStatistics(BaseModel):
        start: datetime
        end: datetime
        represent: "StatisticsSchema.RepresentEnum"
