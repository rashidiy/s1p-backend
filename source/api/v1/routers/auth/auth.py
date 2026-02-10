from datetime import timedelta
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import AuthSchema
from db import get_session
from db.models import User, Company
from utils.managers import PasswordManager, JWTManager, TokenType
from . import router


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
