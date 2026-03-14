import uuid
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from api.v1.schemas.validators import PasswordValidator


class AuthSchema:
    class BearerToken(BaseModel):
        type: str = "Bearer"
        access: str
        refresh: str

    class AuthorizedResponse(BaseModel):
        id: uuid.UUID
        first_name: str = Field(..., max_length=255)
        last_name: Optional[str] = Field(None, max_length=255)
        phone: Optional[str] = Field(None, max_length=50)
        is_active: bool
        must_change_password: bool = False
        credentials: "AuthSchema.BearerToken"

    class PasswordRequiredResponse(BaseModel):
        must_change_password: bool = True
        temporary_token: str

    class ForgotPasswordRequest(BaseModel):
        email: EmailStr

    class ResetPasswordRequest(PasswordValidator, BaseModel):
        old_password: str = Field(..., min_length=1)
        new_password: str = Field(..., min_length=8, max_length=100)

    class SetPasswordRequest(PasswordValidator, BaseModel):
        token: str
        new_password: str = Field(..., min_length=8, max_length=100)
