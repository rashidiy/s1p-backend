import uuid

from pydantic import BaseModel, constr


class SipuniSchema:
    class SipuniCreateRequest(BaseModel):
        company_name: constr(max_length=255)
        cabinet_id: constr(max_length=25)
        security_key: constr(max_length=255)
        partner_name: constr(max_length=255) | None = None
        partner_contact: constr(max_length=255) | None = None
        comment: constr(max_length=1024) | None = None

    class SipuniUpdateRequest(BaseModel):
        id: uuid.UUID
        company_name: constr(max_length=255) | None = None
        cabinet_id: constr(max_length=25) | None = None
        security_key: constr(max_length=255) | None = None
        partner_name: constr(max_length=255) | None = None
        partner_contact: constr(max_length=255) | None = None
        comment: constr(max_length=1024) | None = None

    class SipuniResponse(BaseModel):
        id: uuid.UUID
        company_name: constr(max_length=255)
        cabinet_id: constr(max_length=25)
        security_key: constr(max_length=255)
        user_id: uuid.UUID
        token: constr(min_length=64, max_length=64)
        partner_name: constr(max_length=255) | None = None
        partner_contact: constr(max_length=255) | None = None
        comment: constr(max_length=1024) | None = None
