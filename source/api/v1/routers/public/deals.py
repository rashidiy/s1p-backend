"""
Public API — Deals (read-only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.deal import Deal
from api.v1.schemas.public import PublicDealResponse, PublicPaginatedResponse
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/deals", tags=["Public API — Deals"])


@router.get("", response_model=PublicPaginatedResponse)
async def list_deals(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List deals for the company."""
    company_id, _ = api_key_info

    conditions = [
        Deal.company_id == company_id,
        Deal.deleted_at.is_(None),
    ]

    total = await session.scalar(
        select(func.count()).select_from(Deal).where(and_(*conditions))
    ) or 0

    query = (
        select(Deal)
        .where(and_(*conditions))
        .order_by(Deal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(query)
    items = result.scalars().all()

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

    return PublicPaginatedResponse(
        items=data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )
