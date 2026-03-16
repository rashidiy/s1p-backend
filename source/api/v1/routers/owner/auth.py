"""
Owner authentication endpoints
"""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas.auth import AuthSchema
from core.config import AppConfig
from db import get_session
from db.models.owner import Owner
from db.models.enums import RoleEnum
from api.v1.schemas.owner import OwnerWithCredentials, OwnerResponse
from utils.managers import PasswordManager, JWTManager, TokenType
from utils.services.email_service import EmailService
from utils.services.lockout import is_locked, record_failed_login, clear_failed_logins

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["Owner Auth"])


def _set_auth_cookies(response: Response, credentials: dict):
    """Set httpOnly cookies for access and refresh tokens."""
    if "access" in credentials:
        response.set_cookie(
            key="access_token",
            value=credentials["access"],
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    if "refresh" in credentials:
        response.set_cookie(
            key="refresh_token",
            value=credentials["refresh"],
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )


def _clear_auth_cookies(response: Response):
    """Clear auth cookies."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


class OwnerLoginRequest(BaseModel):
    """Owner login request schema"""
    email: EmailStr
    password: str


@router.post('/login')
@limiter.limit("5/minute")
async def login_owner(
    data: OwnerLoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session)
):
    """
    Owner login

    Returns JWT tokens for authenticated owner.
    If the owner has a temporary password, returns a restricted token
    that only works with set-password.
    """
    # Check account lockout before attempting authentication
    if await is_locked(data.email):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed login attempts",
        )

    owner = await Owner.get(email=data.email, session=session)
    if not owner:
        await record_failed_login(data.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not owner.password_hash or not PasswordManager.verify(data.password, owner.password_hash):
        await record_failed_login(data.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner account is inactive"
        )

    # Clear failed login counter on successful authentication
    await clear_failed_logins(data.email)

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

    _set_auth_cookies(response, owner.credentials)

    return owner


@router.post('/logout')
async def logout_owner(response: Response):
    """Logout by clearing auth cookies"""
    _clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.get('/me', response_model=OwnerResponse)
@limiter.limit("5/minute")
async def get_current_owner(request: Request, owner: Owner = Owner.current()):
    """
    Get current owner profile

    Requires authentication via JWT token.
    """
    return owner


@router.post('/reset-password')
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    data: AuthSchema.ResetPasswordRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Reset owner password (authenticated owner who knows their current password).

    Requires old password for verification.
    """
    # Telegram users have no password — they cannot use password reset
    if not owner.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset not available for Telegram accounts",
        )

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
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
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
@limiter.limit("5/minute")
async def set_password(
    request: Request,
    response: Response,
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

    _set_auth_cookies(response, owner.credentials)

    return owner
