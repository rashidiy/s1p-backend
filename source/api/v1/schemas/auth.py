import uuid

from pydantic import BaseModel, EmailStr, Field

from api.v1.schemas.validators import PasswordValidator


class AuthSchema:
    class RegisterRequest(PasswordValidator, BaseModel):
        first_name: str = Field(..., max_length=255)
        last_name: str = Field(..., max_length=255)
        email: EmailStr
        password: str = Field(..., min_length=8)

    class BearerToken(BaseModel):
        type: str = "Bearer"
        access: str
        refresh: str

    class LoginRequest(BaseModel):
        email: EmailStr
        password: str

    class AuthorizedResponse(BaseModel):
        id: uuid.UUID
        first_name: str = Field(..., max_length=255)
        last_name: str = Field(..., max_length=255)
        email: str = Field(..., max_length=2048)
        is_active: bool
        credentials: "AuthSchema.BearerToken"
