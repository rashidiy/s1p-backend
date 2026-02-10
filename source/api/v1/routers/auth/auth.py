import logging
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import AuthSchema
from core.config import AppConfig
from db import get_session
from db.models import User, Company
from utils.managers import PasswordManager, JWTManager, TokenType
from utils.services.email_service import EmailService
from . import router

logger = logging.getLogger(__name__)


def _extract_subdomain(request: Request) -> str:
    """
    Extract company subdomain from Origin header.

    Expected Origin: https://mycompany.siptools.com or http://mycompany.localhost:3000
    Returns the first part of the hostname as the subdomain.
    """
    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Origin header is required",
        )

    hostname = urlparse(origin).hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Origin header",
        )

    subdomain = hostname.split(".")[0]
    if not subdomain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine company from Origin",
        )

    return subdomain


async def _resolve_company(subdomain: str, session: AsyncSession) -> Company:
    """Resolve a Company from subdomain, raise 404 if not found."""
    company = await Company.get(subdomain=subdomain, session=session)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company is inactive",
        )
    return company


@router.post('/login', response_model=AuthSchema.AuthorizedResponse)
async def login(
    data: AuthSchema.LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Login to a company.

    Company is identified by the Origin header (subdomain).
    Each user can have separate credentials per company.
    """
    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    user = await User.get(email=data.email, company_id=company.id, session=session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    if not PasswordManager.verify(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email or password incorrect.")

    # Generate credentials with multi-tenant support
    user.credentials = JWTManager.generate_credentials(
        sub=user.id,
        company_id=user.company_id,
        role=user.role.value if user.role else None,
        permissions=user.permissions or [],
        access_duration=timedelta(days=15)
    )
    user.must_change_password = not user.email_verified
    return user


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh"""
    refresh_token: str


@router.post('/refresh')
async def refresh_token(data: RefreshTokenRequest):
    """Refresh access token using refresh token"""
    payload = JWTManager.verify(data.refresh_token, TokenType.REFRESH)
    return {
        "access": JWTManager.create(
            sub=payload.sub,
            token_type=TokenType.ACCESS,
            company_id=payload.company_id,
            role=payload.role,
            permissions=payload.permissions,
            data=payload.data
        )
    }


@router.post('/set-password')
async def set_password(
    data: AuthSchema.SetPasswordRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Set new password on first login (replaces temporary password).

    Only available for users who haven't changed their temporary password yet
    (email_verified=False). The user must be authenticated via JWT from login.
    """
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password has already been set. Use change-password instead.",
        )

    user.password_hash = PasswordManager.hash(data.new_password)
    user.email_verified = True
    await user.update(session=session)

    return {"message": "Password set successfully"}


@router.post('/reset-password')
async def reset_password(
    data: AuthSchema.ResetPasswordRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Reset password (authenticated user who knows their current password).

    Requires old password for verification.
    """
    if not PasswordManager.verify(data.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid old password",
        )

    user.password_hash = PasswordManager.hash(data.new_password)
    user.email_verified = True
    await user.update(session=session)

    return {"message": "Password reset successfully"}


@router.post('/forgot-password')
async def forgot_password(
    data: AuthSchema.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Request a password reset email.

    Company is identified by the Origin header (subdomain).
    Always returns 200 to prevent email enumeration.
    """
    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    user = await User.get(email=data.email, company_id=company.id, session=session)
    if user:
        token = JWTManager.create(
            sub=user.id,
            token_type=TokenType.TEMPORARY,
            company_id=user.company_id,
            duration=timedelta(hours=1),
            data={"purpose": "password_reset"},
        )
        reset_url = f"{AppConfig.BASE_URL}/update-password"
        EmailService.send_password_reset(
            background_tasks=background_tasks,
            to_email=user.email,
            reset_token=token,
            reset_url=reset_url,
            company_name=company.name,
        )

    return {"message": "If the email exists, a reset link has been sent"}


@router.post('/update-password')
async def update_password(
    data: AuthSchema.UpdatePasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Update password using a token from the forgot-password email.

    No old password required — the token itself grants permission.
    """
    payload = JWTManager.verify(data.token, TokenType.TEMPORARY)
    if not payload.data or payload.data.get("purpose") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token",
        )

    user = await User.get(id=payload.sub, session=session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.password_hash = PasswordManager.hash(data.new_password)
    user.email_verified = True
    await user.update(session=session)

    return {"message": "Password updated successfully"}
