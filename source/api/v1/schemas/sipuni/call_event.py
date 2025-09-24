from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from db.models.enums import CallStatusEnum


class SipuniEventSchema:
    class HangupEvent(BaseModel):
        event: str
        call_id: str
        record_link: str = Field(alias='call_record_link')
        status: CallStatusEnum
        pbxdstnum: Optional[str] = None
        short_dst_num: str
        short_src_num: str
        dst_num: Optional[str] = None
        dst_type: str
        src_num: str
        src_type: str
        operator: str = Field(alias='last_called')
        transfer_from: Optional[str] = None
        tree_name: Optional[str] = Field(alias='treeName')
        tree_number: Optional[str] = Field(alias='treeNumber')
        user_id: Optional[str] = None
        call_start: datetime = Field(alias='call_start_timestamp')
        call_end: datetime = Field(alias='timestamp')

        @field_validator('operator', mode='before')
        def validate_last_called(cls, v):
            return v.split('&')[-1]

        @field_validator('call_start', 'call_end', mode='before')
        def validate_start_timestamp(cls, v: int):
            return datetime.fromtimestamp(int(v))

        @property
        def duration(self) -> int:
            return int((self.call_end - self.call_start).total_seconds())
