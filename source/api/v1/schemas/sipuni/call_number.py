from pydantic import BaseModel, field_validator, constr, conint

from utils.validators import validate_phone_number


class CallSchema:
    class ExternalCallRequest(BaseModel):
        token: constr(min_length=64, max_length=64)
        phone1: str
        phone2: str
        bridge_start: constr(max_length=100) = 201
        bridge_end: constr(max_length=100) = 201

        @field_validator('phone1', 'phone2')
        def validate_phone(cls, phone):
            return validate_phone_number(phone)

    class CallNumberRequest(BaseModel):
        token: constr(min_length=64, max_length=64)
        phone: str
        sip_number: str
        reverse: bool
        antiaon: bool

        @field_validator('phone')
        def validate_phone(cls, phone):
            return validate_phone_number(phone)

    class CallTreeRequest(BaseModel):
        token: constr(min_length=64, max_length=64)
        phone: str
        sip_number: str
        tree: str
        reverse: bool
        attempt_duration: conint(gt=30) = 30

        @field_validator('phone')
        def validate_sip_number(cls, phone):
            return validate_phone_number(phone)
