from typing import Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    event: str
    call_id: str
    src_num: str
    src_type: Literal['1', '2']
    dst_num: Optional[str] = None
    dst_type: Optional[Literal['1', '2']] = None
    timestamp: int
    short_src_num: Optional[str] = None
    short_dst_num: Optional[str] = None


class CallEvent(BaseEvent):
    event: Literal['1']
    is_inner_call: Optional[Literal['0', '1']] = None
    roistat: Optional[str] = None
    roistat_number: Optional[str] = None
    roistat_market: Optional[str] = None


class AnswerEvent(BaseEvent):
    event: Literal['3']


class HangupBase(BaseEvent):
    status: Literal["ANSWER", "BUSY", "NOANSWER", "CANCEL", "CONGESTION", "CHANUNAVAIL"]
    call_start_timestamp: int
    call_answer_timestamp: int
    call_record_link: Optional[str] = None


class HangupEvent(HangupBase):
    event: Literal['2']
    roistatgoogleid: Optional[str] = None


class SecondaryHangupEvent(HangupBase):
    event: Literal['4']


SipuniEvent = Annotated[
    Union[CallEvent, HangupEvent, AnswerEvent, SecondaryHangupEvent],
    Field(discriminator="event")
]
