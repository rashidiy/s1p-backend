"""
Deals management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

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
from db.models.enums import RoleEnum
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.DEALS_WRITE)
async def create_deal(
    data: DealCreateRequest,
    user: User = User.current(),
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


@router.get("", response_model=PaginatedResponse)
@require_permissions(Permissions.DEALS_READ)
async def list_deals(
    user: User = User.current(),
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

    Operators only see their assigned deals. Admins and Managers see all company deals.
    """
    query = select(Deal).where(
        Deal.company_id == user.company_id,
        Deal.deleted_at.is_(None)
    )

    # Operator scoping: operators only see their assigned deals
    if user.role == RoleEnum.COMPANY_OPERATOR:
        query = query.where(Deal.assigned_to == user.id)
    elif my_deals:
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
        query = query.where(Deal.amount >= min_value)
    if max_value is not None:
        query = query.where(Deal.amount <= max_value)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Subqueries for related names (avoids N+1 queries)
    contact_name_subquery = (
        select(func.trim(func.concat(Contact.first_name, ' ', func.coalesce(Contact.last_name, ''))))
        .where(Contact.id == Deal.contact_id)
        .correlate(Deal)
        .scalar_subquery()
    )
    assignee_name_subquery = (
        select(func.trim(func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))))
        .where(User.id == Deal.assigned_to)
        .correlate(Deal)
        .scalar_subquery()
    )

    # Paginate with name subqueries
    query = query.add_columns(
        contact_name_subquery.label('contact_name'),
        assignee_name_subquery.label('assigned_to_name')
    )
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Deal.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_deals = []
    for row in rows:
        deal = row[0]
        weighted_value = float(deal.amount or 0) * (deal.probability or 0) / 100

        deal_dict = {
            **{k: v for k, v in deal.__dict__.items() if not k.startswith('_')},
            "contact_name": row.contact_name,
            "assigned_to_name": row.assigned_to_name,
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


@router.get("/pipeline/summary")
@require_permissions(Permissions.DEALS_READ)
async def get_pipeline_summary(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get pipeline summary

    Returns deal counts and values by stage.
    """
    # Get all active deals
    query = select(Deal).where(
        Deal.company_id == user.company_id,
        Deal.stage.notin_([DealStageEnum.CLOSED_WON, DealStageEnum.CLOSED_LOST])
    )
    result = await session.execute(query)
    deals = result.scalars().all()

    # Group by stage
    summary = {}
    for stage in DealStageEnum:
        stage_deals = [d for d in deals if d.stage == stage]
        summary[stage.value] = {
            "count": len(stage_deals),
            "total_value": sum(float(d.amount or 0) for d in stage_deals),
            "weighted_value": sum(float(d.amount or 0) * (d.probability or 0) / 100 for d in stage_deals)
        }

    # Overall stats
    total_deals = len(deals)
    total_value = sum(float(d.amount or 0) for d in deals)
    weighted_value = sum(float(d.amount or 0) * (d.probability or 0) / 100 for d in deals)

    return {
        "by_stage": summary,
        "overall": {
            "total_deals": total_deals,
            "total_value": total_value,
            "weighted_value": round(weighted_value, 2)
        }
    }


@router.get("/{deal_id}", response_model=DealResponse)
@require_permissions(Permissions.DEALS_READ)
async def get_deal(
    deal_id: UUID,
    user: User = User.current(),
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
    weighted_value = float(deal.amount or 0) * (deal.probability or 0) / 100

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
    user: User = User.current(),
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
    user: User = User.current(),
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
    user: User = User.current(),
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

    deal.stage = DealStageEnum.CLOSED_WON
    deal.closed_date = datetime.now(timezone.utc).date()
    deal.probability = 100
    deal.win_reason = win_reason

    await deal.update(session=session)

    return deal


@router.post("/{deal_id}/lose", response_model=DealResponse)
@require_permissions(Permissions.DEALS_WRITE)
async def mark_deal_lost(
    deal_id: UUID,
    loss_reason: Optional[str] = Query(None),
    user: User = User.current(),
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

    deal.stage = DealStageEnum.CLOSED_LOST
    deal.closed_date = datetime.now(timezone.utc).date()
    deal.probability = 0
    deal.loss_reason = loss_reason

    await deal.update(session=session)

    return deal
