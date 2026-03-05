"""
Owner authentication endpoints
"""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas.auth import AuthSchema
from core.config import AppConfig
from db import get_session
from db.models.owner import Owner
from db.models.enums import RoleEnum
from api.v1.schemas.owner import OwnerWithCredentials, OwnerResponse
from utils.managers import PasswordManager, JWTManager, TokenType
from utils.services.email_service import EmailService

router = APIRouter(prefix="/auth", tags=["Owner Auth"])


class OwnerLoginRequest(BaseModel):
    """Owner login request schema"""
    email: EmailStr
    password: str


@router.post('/login')
async def login_owner(
    data: OwnerLoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Owner login

    Returns JWT tokens for authenticated owner.
    If the owner has a temporary password, returns a restricted token
    that only works with set-password.
    """
    owner = await Owner.get(email=data.email, session=session)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not PasswordManager.verify(data.password, owner.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid email or password"
        )

    if not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner account is inactive"
        )

    # If owner hasn't changed temporary password, return restricted token
    if not owner.email_verified:
        temporary_token = JWTManager.create(
            sub=owner.id,
            token_type=TokenType.TEMPORARY,
            duration=timedelta(hours=1),
            data={"purpose": "set_password"},
        )
        return AuthSchema.PasswordRequiredResponse(temporary_token=temporary_token)

    # Generate full JWT credentials
    owner.credentials = JWTManager.generate_credentials(
        sub=owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"]
    )
    owner.must_change_password = False

    return owner


@router.get('/me', response_model=OwnerResponse)
async def get_current_owner(owner: Owner = Owner.current()):
    """
    Get current owner profile

    Requires authentication via JWT token.
    """
    return owner


@router.post('/reset-password')
async def reset_password(
    data: AuthSchema.ResetPasswordRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Reset owner password (authenticated owner who knows their current password).

    Requires old password for verification.
    """
    if not PasswordManager.verify(data.old_password, owner.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid old password",
        )

    owner.password_hash = PasswordManager.hash(data.new_password)
    owner.email_verified = True
    await owner.update(session=session)

    return {"message": "Password reset successfully"}


@router.post('/forgot-password')
async def forgot_password(
    data: AuthSchema.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Request a password reset email for owner.

    Always returns 200 to prevent email enumeration.
    """
    owner = await Owner.get(email=data.email, session=session)
    if owner:
        token = JWTManager.create(
            sub=owner.id,
            token_type=TokenType.TEMPORARY,
            duration=timedelta(hours=1),
            data={"purpose": "owner_password_reset"},
        )
        reset_url = f"{AppConfig.BASE_URL}/owner/set-password"
        EmailService.send_password_reset(
            background_tasks=background_tasks,
            to_email=owner.email,
            reset_token=token,
            reset_url=reset_url,
            company_name="S1P CRM",
        )

    return {"message": "If the email exists, a reset link has been sent"}


@router.post('/set-password', response_model=OwnerWithCredentials)
async def set_password(
    data: AuthSchema.SetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Set new owner password using a temporary token.

    Works for both flows:
    - First login: token from login response (purpose=set_password)
    - Forgot password: token from reset email (purpose=owner_password_reset)

    Returns full access/refresh credentials on success.
    """
    payload = JWTManager.verify(data.token, TokenType.TEMPORARY)
    purpose = payload.data.get("purpose") if payload.data else None
    if purpose not in ("set_password", "owner_password_reset"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token",
        )

    owner = await Owner.get(id=payload.sub, session=session)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner not found",
        )

    owner.password_hash = PasswordManager.hash(data.new_password)
    owner.email_verified = True
    await owner.update(session=session)

    # Return full credentials
    owner.credentials = JWTManager.generate_credentials(
        sub=owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"],
    )
    owner.must_change_password = False
    return owner
