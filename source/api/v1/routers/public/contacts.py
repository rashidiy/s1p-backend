"""
Public API — Contacts (read-only)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.contact import Contact
from api.v1.schemas.public import PublicContactResponse, PublicPaginatedResponse
from utils.api_key_auth import get_api_key_company

router = APIRouter(prefix="/contacts", tags=["Public API — Contacts"])


@router.get("", response_model=PublicPaginatedResponse)
async def list_contacts(
    api_key_info: tuple[UUID, UUID] = Depends(get_api_key_company),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List contacts for the company."""
    company_id, _ = api_key_info

    conditions = [
        Contact.company_id == company_id,
        Contact.deleted_at.is_(None),
    ]

    total = await session.scalar(
        select(func.count()).select_from(Contact).where(and_(*conditions))
    ) or 0

    query = (
        select(Contact)
        .where(and_(*conditions))
        .order_by(Contact.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(query)
    items = result.scalars().all()

    return PublicPaginatedResponse(
        items=[PublicContactResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )
