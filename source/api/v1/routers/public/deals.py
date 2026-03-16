"""
Public API — Deals (read-only)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.deal import Deal
from api.v1.schemas.public import (
    PublicDealResponse,
    CursorPaginatedResponse,
    encode_cursor,
    decode_cursor,
)
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/deals", tags=["Public API — Deals"])


@router.get("", response_model=CursorPaginatedResponse)
async def list_deals(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    created_from: Optional[datetime] = Query(None, alias="from", description="Filter: created_at >= this datetime"),
    created_to: Optional[datetime] = Query(None, alias="to", description="Filter: created_at <= this datetime"),
):
    """List deals for the company."""
    company_id, _ = api_key_info

    conditions = [
        Deal.company_id == company_id,
        Deal.deleted_at.is_(None),
    ]

    # Date range filters
    if created_from:
        conditions.append(Deal.created_at >= created_from)
    if created_to:
        conditions.append(Deal.created_at <= created_to)

    # Cursor filter
    if cursor:
        try:
            cursor_id = decode_cursor(cursor)
            cursor_uuid = UUID(cursor_id)
            conditions.append(Deal.id < cursor_uuid)
        except (ValueError, Exception):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor"
            )

    query = (
        select(Deal)
        .where(and_(*conditions))
        .order_by(Deal.id.desc())
        .limit(limit + 1)  # Fetch one extra to determine has_more
    )

    result = await session.execute(query)
    items = list(result.scalars().all())

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    data = []
    for deal in items:
        data.append(PublicDealResponse(
            id=deal.id,
            title=deal.title,
            stage=deal.stage.value if deal.stage else None,
            amount=float(deal.amount) if deal.amount else None,
            currency=deal.currency,
            probability=deal.probability,
            expected_close_date=deal.expected_close_date,
            contact_id=deal.contact_id,
            lead_id=deal.lead_id,
            assigned_to=deal.assigned_to,
            custom_fields=deal.custom_fields,
            created_at=deal.created_at,
            updated_at=deal.updated_at,
        ))

    next_cursor = encode_cursor(items[-1].id) if items and has_more else None

    return CursorPaginatedResponse(
        data=data,
        cursor=next_cursor,
        has_more=has_more,
    )
