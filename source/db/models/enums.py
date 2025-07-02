import enum


class CallStatusEnum(enum.Enum):
    ANSWER = 'ANSWER'
    BUSY = 'BUSY'
    NOANSWER = 'NOANSWER'
    CANCEL = 'CANCEL'
    CONGESTION = 'CONGESTION'
    CHANUNAVAIL = 'CHANUNAVAIL'
