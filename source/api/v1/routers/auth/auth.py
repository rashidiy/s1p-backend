import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import AuthSchema
from core.config import AppConfig
from db import get_session
from db.models import User, Company
from utils.managers import PasswordManager, JWTManager, TokenType
from utils.services.email_service import EmailService
from utils.services.lockout import is_locked, record_failed_login, clear_failed_logins
from . import router

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)


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


def _extract_subdomain(request: Request) -> str:
    """
    Extract company subdomain from Origin header.

    Expected Origin: https://mycompany.s1p.com or http://mycompany.localhost:3000
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
@limiter.limit("5/minute")
async def login(
    data: AuthSchema.LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Login to a company.

    Company is identified by the Origin header (subdomain).
    If the user has a temporary password (email_verified=False),
    returns a restricted token that only works with set-password.
    """
    # Check account lockout before attempting authentication
    if await is_locked(data.email):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed login attempts. Try again in 15 minutes.",
        )

    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    user = await User.get(email=data.email, company_id=company.id, session=session)
    if not user or not user.password_hash or not PasswordManager.verify(data.password, user.password_hash):
        await record_failed_login(data.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    # Clear failed login counter on successful authentication
    await clear_failed_logins(data.email)

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
        access_duration=timedelta(minutes=30)
    )
    user.must_change_password = False

    _set_auth_cookies(response, user.credentials)

    return user


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh"""
    refresh_token: Optional[str] = None


@router.post('/refresh')
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    response: Response,
    data: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
):
    """Refresh access token using refresh token"""
    token = data.refresh_token or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required.")
    payload = JWTManager.verify(token, TokenType.REFRESH)

    user = await User.get(id=payload.sub, session=session)
    if not user or user.deleted_at or user.is_suspended or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired or invalid.")

    new_access = JWTManager.create(
        sub=payload.sub,
        token_type=TokenType.ACCESS,
        company_id=payload.company_id,
        role=payload.role,
        permissions=payload.permissions,
        data=payload.data
    )

    _set_auth_cookies(response, {"access": new_access})

    return {"access": new_access}


@router.post('/logout')
async def logout(response: Response):
    """Logout by clearing auth cookies"""
    _clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.post('/set-password', response_model=AuthSchema.AuthorizedResponse)
@limiter.limit("5/minute")
async def set_password(
    request: Request,
    response: Response,
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
        access_duration=timedelta(minutes=30),
    )
    user.must_change_password = False

    _set_auth_cookies(response, user.credentials)

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
    # Telegram users have no password — they cannot use password reset
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset not available for Telegram accounts",
        )

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
@limiter.limit("3/hour")
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
