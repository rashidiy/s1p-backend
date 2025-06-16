import uuid

from pydantic import BaseModel, constr, EmailStr


class AuthSchema:
    class RegisterRequest(BaseModel):
        first_name: constr(max_length=255)
        last_name: constr(max_length=255)
        email: EmailStr
        password: constr(min_length=8)

    class BearerToken(BaseModel):
        type: str = "Bearer"
        access: str
        refresh: str

    class LoginRequest(BaseModel):
        email: EmailStr
        password: constr(min_length=8)

    class AuthorizedResponse(BaseModel):
        id: uuid.UUID
        first_name: constr(max_length=255)
        last_name: constr(max_length=255)
        email: constr(max_length=2048)
        is_active: bool
        credentials: "AuthSchema.BearerToken"
