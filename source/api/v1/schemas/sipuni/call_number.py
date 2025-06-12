from pydantic import BaseModel, field_validator


class ExternalCallRequest(BaseModel):
    phone1: str
    phone2: str
    secret: str
    bridge_start: str
    bridge_end: str

    @field_validator('phone1', 'phone2', 'bridge_start', 'bridge_end')
    def validate_phone1_phone2(cls, phone_number):
        return phone_number
