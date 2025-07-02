from typing import Optional

from pydantic import BaseModel, Field, field_validator

from db.models.enums import CallStatusEnum


class SipuniEventSchema:
    class HangupEvent(BaseModel):
        event: str
        call_id: str
        record_link: str = Field(alias='call_record_link')
        status: CallStatusEnum
        call_start_timestamp: int
        call_end_timestamp: Optional[int] = None
        pbxdstnum: Optional[str] = None
        short_dst_num: str
        short_src_num: str
        dst_num: Optional[str] = None
        dst_type: str
        src_num: str
        src_type: str
        last_called: str | list
        timestamp: int
        transfer_from: Optional[str] = None
        treeName: Optional[str] = None
        treeNumber: Optional[str] = None
        user_id: Optional[str] = None

        @field_validator('last_called')
        def validate_last_called(cls, v):
            return v.split('&')
