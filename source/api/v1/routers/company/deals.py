"""
Deals management endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, case, literal
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
from utils.services.webhook import fire_webhook_event

router = APIRouter(prefix="/deals", tags=["Deals"])


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED, response_description="The newly created deal")
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
        select(
            case(
                (Contact.deleted_at.isnot(None), literal("(deleted)")),
                else_=func.trim(func.concat(Contact.first_name, ' ', func.coalesce(Contact.last_name, '')))
            )
        )
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
    # Use SQL aggregation instead of loading all deals
    stage_query = (
        select(
            Deal.stage,
            func.count().label('count'),
            func.coalesce(func.sum(Deal.amount), 0).label('total_value'),
            func.coalesce(func.sum(Deal.amount * Deal.probability / 100), 0).label('weighted_value')
        )
        .where(
            Deal.company_id == user.company_id,
            Deal.deleted_at.is_(None),
            Deal.stage.notin_([DealStageEnum.CLOSED_WON, DealStageEnum.CLOSED_LOST])
        )
    )

    # Operators only see their own deals in pipeline
    if user.role == RoleEnum.COMPANY_OPERATOR:
        stage_query = stage_query.where(Deal.assigned_to == user.id)

    stage_query = stage_query.group_by(Deal.stage)
    result = await session.execute(stage_query)
    stage_rows = result.all()

    # Build summary with all stages (including ones with 0 deals)
    summary = {}
    total_deals = 0
    total_value = 0.0
    weighted_value = 0.0
    for stage in DealStageEnum:
        summary[stage.value] = {"count": 0, "total_value": 0.0, "weighted_value": 0.0}

    for stage_enum, count, stage_total, stage_weighted in stage_rows:
        summary[stage_enum.value] = {
            "count": count,
            "total_value": float(stage_total),
            "weighted_value": round(float(stage_weighted), 2)
        }
        total_deals += count
        total_value += float(stage_total)
        weighted_value += float(stage_weighted)

    return {
        "by_stage": summary,
        "overall": {
            "total_deals": total_deals,
            "total_value": total_value,
            "weighted_value": round(weighted_value, 2)
        }
    }


@router.get("/{deal_id}", response_model=DealResponse, response_description="Deal details with contact name and weighted value")
@require_permissions(Permissions.DEALS_READ)
async def get_deal(
    deal_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get deal details

    Returns full deal information with contact name, assignee name, and weighted value.
    Operators can only view their own assigned deals.
    """
    deal = await Deal.get_or_404(
        session=session,
        id=deal_id,
        company_id=user.company_id
    )

    # Operators can only see their own deals
    if user.role == RoleEnum.COMPANY_OPERATOR and deal.assigned_to != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    # Get contact name (handle soft-deleted contacts)
    contact_name = None
    if deal.contact_id:
        result = await session.execute(
            select(Contact).where(Contact.id == deal.contact_id)
        )
        contact = result.scalar_one_or_none()
        if contact:
            if contact.deleted_at is not None:
                contact_name = "(deleted)"
            else:
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
    background_tasks: BackgroundTasks,
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

    old_stage = deal.stage

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

    # Telegram notification if stage changed
    if data.stage and deal.stage != old_stage:
        assigned_name = None
        if deal.assigned_to:
            a = await User.get(session=session, id=deal.assigned_to)
            if a:
                assigned_name = a.full_name
        background_tasks.add_task(
            _notify_deal_stage_change,
            user.company_id, deal.id, deal.title,
            old_stage.value if old_stage else "", deal.stage.value,
            float(deal.amount) if deal.amount else None, assigned_name, deal.assigned_to
        )

        # Fire outbound webhook for stage change
        await fire_webhook_event(
            company_id=user.company_id,
            event_type="deal.stage_changed",
            data={
                "id": str(deal.id),
                "title": deal.title,
                "old_stage": old_stage.value if old_stage else None,
                "new_stage": deal.stage.value,
                "amount": float(deal.amount) if deal.amount else None,
            },
            session=session,
        )

    return deal


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.DEALS_DELETE)
async def delete_deal(
    deal_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False)
):
    """
    Delete a deal

    Soft delete by default. Use hard=true for permanent deletion.
    Requires DEALS_DELETE permission.
    """
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
    background_tasks: BackgroundTasks,
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

    old_stage = deal.stage
    deal.stage = DealStageEnum.CLOSED_WON
    deal.closed_date = datetime.now(timezone.utc).date()
    deal.probability = 100
    deal.win_reason = win_reason

    await deal.update(session=session)

    assigned_name = None
    if deal.assigned_to:
        a = await User.get(session=session, id=deal.assigned_to)
        if a:
            assigned_name = a.full_name
    background_tasks.add_task(
        _notify_deal_stage_change,
        user.company_id, deal.id, deal.title,
        old_stage.value if old_stage else "", "closed_won",
        float(deal.amount) if deal.amount else None, assigned_name
    )

    await fire_webhook_event(
        company_id=user.company_id,
        event_type="deal.stage_changed",
        data={
            "id": str(deal.id),
            "title": deal.title,
            "old_stage": old_stage.value if old_stage else None,
            "new_stage": "closed_won",
            "amount": float(deal.amount) if deal.amount else None,
        },
        session=session,
    )

    return deal


@router.post("/{deal_id}/lose", response_model=DealResponse)
@require_permissions(Permissions.DEALS_WRITE)
async def mark_deal_lost(
    deal_id: UUID,
    background_tasks: BackgroundTasks,
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

    old_stage = deal.stage
    deal.stage = DealStageEnum.CLOSED_LOST
    deal.closed_date = datetime.now(timezone.utc).date()
    deal.probability = 0
    deal.loss_reason = loss_reason

    await deal.update(session=session)

    assigned_name = None
    if deal.assigned_to:
        a = await User.get(session=session, id=deal.assigned_to)
        if a:
            assigned_name = a.full_name
    background_tasks.add_task(
        _notify_deal_stage_change,
        user.company_id, deal.id, deal.title,
        old_stage.value if old_stage else "", "closed_lost",
        float(deal.amount) if deal.amount else None, assigned_name
    )

    await fire_webhook_event(
        company_id=user.company_id,
        event_type="deal.stage_changed",
        data={
            "id": str(deal.id),
            "title": deal.title,
            "old_stage": old_stage.value if old_stage else None,
            "new_stage": "closed_lost",
            "amount": float(deal.amount) if deal.amount else None,
        },
        session=session,
    )

    return deal


async def _notify_deal_stage_change(company_id, deal_id, deal_title, old_stage, new_stage, amount, assigned_name, assigned_to_id=None):
    """Background task: send Telegram notification for deal stage change."""
    import logging
    from db.base import AsyncDatabaseSession
    from utils.services.telegram_service import TelegramService

    try:
        async for session in AsyncDatabaseSession()():
            await TelegramService.notify_deal_stage_change(
                session=session,
                company_id=company_id,
                deal_id=deal_id,
                deal_title=deal_title,
                old_stage=old_stage,
                new_stage=new_stage,
                amount=amount,
                assigned_to_name=assigned_name,
                assigned_to_id=assigned_to_id,
            )
    except Exception as e:
        logging.getLogger(__name__).error(f"Telegram deal_stage notification failed: {e}", exc_info=True)
