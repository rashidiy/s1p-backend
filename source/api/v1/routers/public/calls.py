"""
Public API — Calls (read-only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.call_event import CallEvent
from api.v1.schemas.public import PublicCallResponse, PublicPaginatedResponse
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/calls", tags=["Public API — Calls"])


@router.get("", response_model=PublicPaginatedResponse)
async def list_calls(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List call events for the company."""
    company_id, _ = api_key_info

    conditions = [
        CallEvent.company_id == company_id,
    ]

    total = await session.scalar(
        select(func.count()).select_from(CallEvent).where(and_(*conditions))
    ) or 0

    query = (
        select(CallEvent)
        .where(and_(*conditions))
        .order_by(CallEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(query)
    items = result.scalars().all()

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

    return PublicPaginatedResponse(
        items=data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )
