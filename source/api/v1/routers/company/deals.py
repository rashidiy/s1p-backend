"""
Deals management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from uuid import UUID
from datetime import datetime

from db import get_session
from db.models.user import User
from db.models.deal import Deal
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.enums import DealStageEnum
from api.v1.schemas.crm import (
    DealCreateRequest,
    DealUpdateRequest,
    DealResponse,
    PaginatedResponse
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.post("/", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.DEALS_WRITE)
async def create_deal(
    data: DealCreateRequest,
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new deal

    Deals represent active sales opportunities with monetary value.
    """
    # Validate contact if provided
    if data.contact_id:
        contact = await Contact.get_or_404(
            session=session,
            id=data.contact_id,
            company_id=user.company_id
        )

    # Validate lead if provided
    if data.lead_id:
        lead = await Lead.get_or_404(
            session=session,
            id=data.lead_id,
            company_id=user.company_id
        )

    # Validate assigned user if provided
    if data.assigned_to:
        assignee = await User.get_or_404(
            session=session,
            id=data.assigned_to,
            company_id=user.company_id
        )

    deal = await Deal.create(
        session=session,
        company_id=user.company_id,
        created_by=user.id,
        **data.model_dump(exclude={'tags'})
    )

    return deal


@router.get("/", response_model=PaginatedResponse)
@require_permissions(Permissions.DEALS_READ)
async def list_deals(
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    stage: Optional[str] = None,
    assigned_to: Optional[UUID] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    my_deals: bool = Query(False, description="Show only my assigned deals")
):
    """
    List all deals with filters

    Pipeline view: filter by stage to see deals in different stages.
    """
    query = select(Deal).where(Deal.company_id == user.company_id)

    # Show only my deals if requested
    if my_deals:
        query = query.where(Deal.assigned_to == user.id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Deal.title.ilike(search_term),
                Deal.description.ilike(search_term)
            )
        )

    # Filters
    if stage:
        try:
            stage_enum = DealStageEnum(stage)
            query = query.where(Deal.stage == stage_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid stage. Must be one of: {[s.value for s in DealStageEnum]}"
            )
    if assigned_to:
        query = query.where(Deal.assigned_to == assigned_to)
    if min_value is not None:
        query = query.where(Deal.value >= min_value)
    if max_value is not None:
        query = query.where(Deal.value <= max_value)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Deal.created_at.desc())

    result = await session.execute(query)
    deals = result.scalars().all()

    # Enhance with related info
    enhanced_deals = []
    for deal in deals:
        # Get contact name
        contact_name = None
        if deal.contact_id:
            contact = await Contact.get(session=session, id=deal.contact_id)
            if contact:
                contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()

        # Get assigned to name
        assigned_to_name = None
        if deal.assigned_to:
            assignee = await User.get(session=session, id=deal.assigned_to)
            if assignee:
                assigned_to_name = assignee.full_name

        # Calculate weighted value
        weighted_value = (deal.value or 0) * (deal.probability or 0) / 100

        deal_dict = {
            **{k: v for k, v in deal.__dict__.items() if not k.startswith('_')},
            "contact_name": contact_name,
            "assigned_to_name": assigned_to_name,
            "weighted_value": round(weighted_value, 2)
        }
        enhanced_deals.append(DealResponse(**deal_dict))

    return PaginatedResponse(
        items=enhanced_deals,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{deal_id}", response_model=DealResponse)
@require_permissions(Permissions.DEALS_READ)
async def get_deal(
    deal_id: UUID,
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """Get deal details"""
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    # Get contact name
    contact_name = None
    if deal.contact_id:
        contact = await Contact.get(session=session, id=deal.contact_id)
        if contact:
            contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()

    # Get assigned to name
    assigned_to_name = None
    if deal.assigned_to:
        assignee = await User.get(session=session, id=deal.assigned_to)
        if assignee:
            assigned_to_name = assignee.full_name

    # Calculate weighted value
    weighted_value = (deal.value or 0) * (deal.probability or 0) / 100

    deal_dict = {
        **{k: v for k, v in deal.__dict__.items() if not k.startswith('_')},
        "contact_name": contact_name,
        "assigned_to_name": assigned_to_name,
        "weighted_value": round(weighted_value, 2)
    }

    return DealResponse(**deal_dict)


@router.put("/{deal_id}", response_model=DealResponse)
@require_permissions(Permissions.DEALS_WRITE)
async def update_deal(
    deal_id: UUID,
    data: DealUpdateRequest,
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Update deal information

    Supports moving deals through pipeline stages.
    """
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    # Validate contact if changing
    if data.contact_id:
        contact = await Contact.get_or_404(
            session=session,
            id=data.contact_id,
            company_id=user.company_id
        )

    # Validate assigned user if changing
    if data.assigned_to:
        assignee = await User.get_or_404(
            session=session,
            id=data.assigned_to,
            company_id=user.company_id
        )

    # Validate stage if changing
    if data.stage:
        try:
            stage_enum = DealStageEnum(data.stage)
            # Auto-set closed_at if marking as won/lost
            if stage_enum in [DealStageEnum.WON, DealStageEnum.LOST] and not deal.closed_at:
                deal.closed_at = datetime.now()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid stage. Must be one of: {[s.value for s in DealStageEnum]}"
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True, exclude={'tags'})
    for field, value in update_data.items():
        setattr(deal, field, value)

    await deal.update(session=session)

    return deal


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.DEALS_DELETE)
async def delete_deal(
    deal_id: UUID,
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False)
):
    """Delete a deal"""
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    await deal.delete(session=session, hard=hard)
    return None


@router.post("/{deal_id}/win", response_model=DealResponse)
@require_permissions(Permissions.DEALS_WRITE)
async def mark_deal_won(
    deal_id: UUID,
    win_reason: Optional[str] = Query(None),
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Mark deal as won

    Records win reason and closes the deal.
    """
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    deal.stage = DealStageEnum.WON
    deal.win_reason = win_reason
    deal.closed_at = datetime.now()
    deal.probability = 100

    await deal.update(session=session)

    return deal


@router.post("/{deal_id}/lose", response_model=DealResponse)
@require_permissions(Permissions.DEALS_WRITE)
async def mark_deal_lost(
    deal_id: UUID,
    loss_reason: Optional[str] = Query(None),
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Mark deal as lost

    Records loss reason and closes the deal.
    """
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    deal.stage = DealStageEnum.LOST
    deal.loss_reason = loss_reason
    deal.closed_at = datetime.now()
    deal.probability = 0

    await deal.update(session=session)

    return deal


@router.get("/pipeline/summary")
@require_permissions(Permissions.DEALS_READ)
async def get_pipeline_summary(
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get pipeline summary

    Returns deal counts and values by stage.
    """
    # Get all active deals
    query = select(Deal).where(
        Deal.company_id == user.company_id,
        Deal.stage.notin_([DealStageEnum.WON, DealStageEnum.LOST])
    )
    result = await session.execute(query)
    deals = result.scalars().all()

    # Group by stage
    summary = {}
    for stage in DealStageEnum:
        stage_deals = [d for d in deals if d.stage == stage]
        summary[stage.value] = {
            "count": len(stage_deals),
            "total_value": sum(d.value or 0 for d in stage_deals),
            "weighted_value": sum((d.value or 0) * (d.probability or 0) / 100 for d in stage_deals)
        }

    # Overall stats
    total_deals = len(deals)
    total_value = sum(d.value or 0 for d in deals)
    weighted_value = sum((d.value or 0) * (d.probability or 0) / 100 for d in deals)

    return {
        "by_stage": summary,
        "overall": {
            "total_deals": total_deals,
            "total_value": total_value,
            "weighted_value": round(weighted_value, 2)
        }
    }
