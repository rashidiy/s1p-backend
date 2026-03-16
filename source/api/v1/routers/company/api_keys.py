"""
API Key management endpoints (internal, JWT-authenticated)

Company admins can create, list, and revoke API keys for public API access.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.api_key import ApiKey
from api.v1.schemas.public import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyListResponse,
)
from utils.permissions import require_permissions, Permissions
from utils.api_key_auth import hash_api_key

router = APIRouter(prefix="/api-keys", tags=["API Keys"])

limiter = Limiter(key_func=get_remote_address)

MAX_KEYS_PER_COMPANY = 10


def generate_api_key() -> str:
    """Generate a secure random API key (s1p_ prefix + 48 random chars)"""
    return f"s1p_{secrets.token_urlsafe(36)}"


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_api_key(
    request: Request,
    data: ApiKeyCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new API key for public API access.

    The full key is returned ONLY in this response. Store it securely.
    Maximum 10 keys per company.
    """
    # Check key limit
    count_query = select(func.count()).select_from(ApiKey).where(
        ApiKey.company_id == user.company_id,
        ApiKey.is_active == True,
    )
    active_count = await session.scalar(count_query) or 0
    if active_count >= MAX_KEYS_PER_COMPANY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_KEYS_PER_COMPANY} active API keys per company.",
        )

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:8]

    api_key = await ApiKey.create(
        session=session,
        company_id=user.company_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=data.name,
    )

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=key_prefix,
        created_at=api_key.created_at,
    )


@router.get("", response_model=ApiKeyListResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def list_api_keys(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """List all API keys for the company."""
    keys = await ApiKey.get_all(
        session=session,
        company_id=user.company_id,
        order_by=(ApiKey.created_at.desc(),),
    )

    return ApiKeyListResponse(
        items=[ApiKeyResponse.model_validate(k) for k in keys],
        total=len(keys),
    )


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
@require_permissions(Permissions.SETTINGS_MANAGE)
async def revoke_api_key(
    request: Request,
    api_key_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Revoke an API key. The key will immediately stop working."""
    api_key = await ApiKey.get_or_404(
        session=session,
        id=api_key_id,
        company_id=user.company_id,
    )

    api_key.is_active = False
    await api_key.update(session=session)
    return None
