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


@router.post('/login')
async def login(
    data: AuthSchema.LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Login to a company.

    Company is identified by the Origin header (subdomain).
    If the user has a temporary password (email_verified=False),
    returns a restricted token that only works with set-password.
    """
    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    user = await User.get(email=data.email, company_id=company.id, session=session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    if not PasswordManager.verify(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email or password incorrect.")

    # If user hasn't changed temporary password, return restricted token
    if not user.email_verified:
        temporary_token = JWTManager.create(
            sub=user.id,
            token_type=TokenType.TEMPORARY,
            company_id=user.company_id,
            duration=timedelta(hours=1),
            data={"purpose": "set_password"},
        )
        return AuthSchema.PasswordRequiredResponse(temporary_token=temporary_token)

    # Generate full credentials
    user.credentials = JWTManager.generate_credentials(
        sub=user.id,
        company_id=user.company_id,
        role=user.role.value if user.role else None,
        permissions=user.permissions or [],
        access_duration=timedelta(days=15)
    )
    user.must_change_password = False
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


@router.post('/set-password', response_model=AuthSchema.AuthorizedResponse)
async def set_password(
    data: AuthSchema.SetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Set new password using a temporary token.

    Works for both flows:
    - First login: token from login response (purpose=set_password)
    - Forgot password: token from reset email (purpose=password_reset)

    Returns full access/refresh credentials on success.
    """
    payload = JWTManager.verify(data.token, TokenType.TEMPORARY)
    purpose = payload.data.get("purpose") if payload.data else None
    if purpose not in ("set_password", "password_reset"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token",
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

    # Return full credentials
    user.credentials = JWTManager.generate_credentials(
        sub=user.id,
        company_id=user.company_id,
        role=user.role.value if user.role else None,
        permissions=user.permissions or [],
        access_duration=timedelta(days=15),
    )
    user.must_change_password = False
    return user


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
        reset_url = f"{AppConfig.BASE_URL}/set-password"
        EmailService.send_password_reset(
            background_tasks=background_tasks,
            to_email=user.email,
            reset_token=token,
            reset_url=reset_url,
            company_name=company.name,
        )

    return {"message": "If the email exists, a reset link has been sent"}
