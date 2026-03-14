"""
Public API — Contacts (read-only)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.contact import Contact
from api.v1.schemas.public import (
    PublicContactResponse,
    CursorPaginatedResponse,
    encode_cursor,
    decode_cursor,
)
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/contacts", tags=["Public API — Contacts"])


@router.get("", response_model=CursorPaginatedResponse)
async def list_contacts(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    created_from: Optional[datetime] = Query(None, alias="from", description="Filter: created_at >= this datetime"),
    created_to: Optional[datetime] = Query(None, alias="to", description="Filter: created_at <= this datetime"),
):
    """List contacts for the company."""
    company_id, _ = api_key_info

    conditions = [
        Contact.company_id == company_id,
        Contact.deleted_at.is_(None),
    ]

    # Date range filters
    if created_from:
        conditions.append(Contact.created_at >= created_from)
    if created_to:
        conditions.append(Contact.created_at <= created_to)

    # Cursor filter
    if cursor:
        try:
            cursor_id = decode_cursor(cursor)
            cursor_uuid = UUID(cursor_id)
            conditions.append(Contact.id < cursor_uuid)
        except (ValueError, Exception):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor"
            )

    query = (
        select(Contact)
        .where(and_(*conditions))
        .order_by(Contact.id.desc())
        .limit(limit + 1)  # Fetch one extra to determine has_more
    )

    result = await session.execute(query)
    items = list(result.scalars().all())

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor = encode_cursor(items[-1].id) if items and has_more else None

    return CursorPaginatedResponse(
        data=[PublicContactResponse.model_validate(c) for c in items],
        cursor=next_cursor,
        has_more=has_more,
    )
