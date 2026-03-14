"""
Public API — Calls (read-only)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.call_event import CallEvent
from api.v1.schemas.public import (
    PublicCallResponse,
    CursorPaginatedResponse,
    encode_cursor,
    decode_cursor,
)
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/calls", tags=["Public API — Calls"])


@router.get("", response_model=CursorPaginatedResponse)
async def list_calls(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    created_from: Optional[datetime] = Query(None, alias="from", description="Filter: created_at >= this datetime"),
    created_to: Optional[datetime] = Query(None, alias="to", description="Filter: created_at <= this datetime"),
):
    """List call events for the company."""
    company_id, _ = api_key_info

    conditions = [
        CallEvent.company_id == company_id,
    ]

    # Date range filters
    if created_from:
        conditions.append(CallEvent.created_at >= created_from)
    if created_to:
        conditions.append(CallEvent.created_at <= created_to)

    # Cursor filter
    if cursor:
        try:
            cursor_id = decode_cursor(cursor)
            cursor_int = int(cursor_id)
            conditions.append(CallEvent.id < cursor_int)
        except (ValueError, Exception):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor"
            )

    query = (
        select(CallEvent)
        .where(and_(*conditions))
        .order_by(CallEvent.id.desc())
        .limit(limit + 1)  # Fetch one extra to determine has_more
    )

    result = await session.execute(query)
    items = list(result.scalars().all())

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    data = []
    for call in items:
        data.append(PublicCallResponse(
            id=call.id,
            phone_1=call.phone_1,
            phone_2=call.phone_2,
            direction=call.direction.value if call.direction else None,
            state=call.state.value if call.state else None,
            duration_sec=call.billing_sec,
            contact_id=call.contact_id,
            lead_id=call.lead_id,
            deal_id=call.deal_id,
            created_at=call.created_at,
            updated_at=call.updated_at,
        ))

    next_cursor = encode_cursor(items[-1].id) if items and has_more else None

    return CursorPaginatedResponse(
        data=data,
        cursor=next_cursor,
        has_more=has_more,
    )
