"""
Public API — Leads (read-only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.lead import Lead
from api.v1.schemas.public import PublicLeadResponse, PublicPaginatedResponse
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/leads", tags=["Public API — Leads"])


@router.get("", response_model=PublicPaginatedResponse)
async def list_leads(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List leads for the company."""
    company_id, _ = api_key_info

    conditions = [
        Lead.company_id == company_id,
        Lead.deleted_at.is_(None),
    ]

    total = await session.scalar(
        select(func.count()).select_from(Lead).where(and_(*conditions))
    ) or 0

    query = (
        select(Lead)
        .where(and_(*conditions))
        .order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(query)
    items = result.scalars().all()

    data = []
    for lead in items:
        data.append(PublicLeadResponse(
            id=lead.id,
            title=lead.title,
            status=lead.status.value if lead.status else None,
            source=lead.source,
            description=lead.description,
            estimated_value=float(lead.estimated_value) if lead.estimated_value else None,
            currency=lead.currency,
            contact_id=lead.contact_id,
            assigned_to=lead.assigned_to,
            custom_fields=lead.custom_fields,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        ))

    return PublicPaginatedResponse(
        items=data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )
