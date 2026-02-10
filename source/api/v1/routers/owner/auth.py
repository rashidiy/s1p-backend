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


@router.post('/login', response_model=OwnerWithCredentials)
async def login_owner(
    data: OwnerLoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Owner login

    Returns JWT tokens for authenticated owner.
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

    # Generate JWT credentials
    owner.credentials = JWTManager.generate_credentials(
        sub=owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"]
    )
    owner.must_change_password = not owner.email_verified

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
        reset_url = f"{AppConfig.BASE_URL}/owner/update-password"
        EmailService.send_password_reset(
            background_tasks=background_tasks,
            to_email=owner.email,
            reset_token=token,
            reset_url=reset_url,
            company_name="SIPtools CRM",
        )

    return {"message": "If the email exists, a reset link has been sent"}


@router.post('/update-password')
async def update_password(
    data: AuthSchema.UpdatePasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Update owner password using a token from the forgot-password email.

    No old password required — the token itself grants permission.
    """
    payload = JWTManager.verify(data.token, TokenType.TEMPORARY)
    if not payload.data or payload.data.get("purpose") != "owner_password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token",
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

    return {"message": "Password updated successfully"}
