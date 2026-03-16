import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from db import get_session
from db.models import User, Company
from utils.managers import JWTManager, TokenType
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


