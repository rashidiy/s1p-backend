"""
API Key authentication for public REST API

Separate from JWT auth. Uses X-API-Key header.
"""

import hashlib
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from db import get_session
from db.models.api_key import ApiKey

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """Hash API key with SHA-256 for storage/lookup"""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_api_key_company(
    raw_key: Optional[str] = Security(api_key_header),
    session: AsyncSession = Depends(get_session),
) -> tuple[UUID, UUID]:
    """
    Authenticate via X-API-Key header. Returns (company_id, api_key_id).

    Raises 401 if key is missing/invalid/revoked.
    """
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(raw_key)

    api_key = await ApiKey.get(
        session=session,
        key_hash=key_hash,
    )

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not api_key.is_active:
        raise HTTPException(status_code=401, detail="API key has been revoked")

    # Update last_used_at
    api_key.last_used_at = func.now()
    await session.commit()

    return api_key.company_id, api_key.id
