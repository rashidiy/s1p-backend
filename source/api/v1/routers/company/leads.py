"""
Leads management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.lead import Lead
from db.models.contact import Contact
from db.models.deal import Deal
from db.models.enums import LeadStatusEnum
from api.v1.schemas.crm import (
    LeadCreateRequest,
    LeadUpdateRequest,
    LeadResponse,
    PaginatedResponse
)
from db.models.enums import RoleEnum
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.LEADS_WRITE)
async def create_lead(
    data: LeadCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new lead

    Leads represent potential sales opportunities. They can be linked to contacts.
    """
    # Validate contact if provided
    if data.contact_id:
        contact = await Contact.get_or_404(
            session=session,
            id=data.contact_id,
            company_id=user.company_id
        )

    # Validate assigned user if provided
    if data.assigned_to:
        assignee = await User.get_or_404(
            session=session,
            id=data.assigned_to,
            company_id=user.company_id
        )

    lead = await Lead.create(
        session=session,
        company_id=user.company_id,
        created_by=user.id,
        **data.model_dump(exclude={'tags'})
    )

    return lead


@router.get("", response_model=PaginatedResponse)
@require_permissions(Permissions.LEADS_READ)
async def list_leads(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    assigned_to: Optional[UUID] = None,
    source: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    my_leads: bool = Query(False, description="Show only my assigned leads")
):
    """
    List all leads with filters

    Operators only see their assigned leads. Admins and Managers see all company leads.
    """
    query = select(Lead).where(
        Lead.company_id == user.company_id,
        Lead.deleted_at.is_(None)
    )

    # Operator scoping: operators only see their assigned leads
    if user.role == RoleEnum.COMPANY_OPERATOR:
        query = query.where(Lead.assigned_to == user.id)
    elif my_leads:
        query = query.where(Lead.assigned_to == user.id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Lead.title.ilike(search_term),
                Lead.description.ilike(search_term)
            )
        )

    # Filters
    if status_filter:
        try:
            status_enum = LeadStatusEnum(status_filter)
            query = query.where(Lead.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {[s.value for s in LeadStatusEnum]}"
            )
    if assigned_to:
        query = query.where(Lead.assigned_to == assigned_to)
    if source:
        query = query.where(Lead.source == source)
    if min_value is not None:
        query = query.where(Lead.estimated_value >= min_value)
    if max_value is not None:
        query = query.where(Lead.estimated_value <= max_value)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Subqueries for related names (avoids N+1 queries)
    contact_name_subquery = (
        select(func.trim(func.concat(Contact.first_name, ' ', func.coalesce(Contact.last_name, ''))))
        .where(Contact.id == Lead.contact_id)
        .correlate(Lead)
        .scalar_subquery()
    )
    assignee_name_subquery = (
        select(func.trim(func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))))
        .where(User.id == Lead.assigned_to)
        .correlate(Lead)
        .scalar_subquery()
    )

    # Paginate with name subqueries
    query = query.add_columns(
        contact_name_subquery.label('contact_name'),
        assignee_name_subquery.label('assigned_to_name')
    )
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Lead.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_leads = []
    for row in rows:
        lead = row[0]
        lead_dict = {
            **{k: v for k, v in lead.__dict__.items() if not k.startswith('_')},
            "contact_name": row.contact_name,
            "assigned_to_name": row.assigned_to_name
        }
        enhanced_leads.append(LeadResponse(**lead_dict))

    return PaginatedResponse(
        items=enhanced_leads,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{lead_id}", response_model=LeadResponse)
@require_permissions(Permissions.LEADS_READ)
async def get_lead(
    lead_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Get lead details"""
    lead = await Lead.get_or_404(
        session=session,
        id=lead_id,
        company_id=user.company_id
    )

    # Get contact name
    contact_name = None
    if lead.contact_id:
        contact = await Contact.get(session=session, id=lead.contact_id)
        if contact:
            contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()

    # Get assigned to name
    assigned_to_name = None
    if lead.assigned_to:
        assignee = await User.get(session=session, id=lead.assigned_to)
        if assignee:
            assigned_to_name = assignee.full_name

    lead_dict = {
        **{k: v for k, v in lead.__dict__.items() if not k.startswith('_')},
        "contact_name": contact_name,
        "assigned_to_name": assigned_to_name
    }

    return LeadResponse(**lead_dict)


@router.put("/{lead_id}", response_model=LeadResponse)
@require_permissions(Permissions.LEADS_WRITE)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update lead information

    Supports status changes through the lead lifecycle.
    """
    lead = await Lead.get_or_404(
        session=session,
        id=lead_id,
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
        setattr(lead, field, value)

    await lead.update(session=session)

    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.LEADS_DELETE)
async def delete_lead(
    lead_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False)
):
    """Delete a lead"""
    lead = await Lead.get_or_404(
        session=session,
        id=lead_id,
        company_id=user.company_id
    )

    await lead.delete(session=session, hard=hard)
    return None


@router.post("/{lead_id}/convert", response_model=dict)
@require_permissions(Permissions.LEADS_WRITE, Permissions.DEALS_WRITE)
async def convert_lead(
    lead_id: UUID,
    create_deal: bool = Query(True, description="Create deal from lead"),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Convert lead to customer

    Optionally creates a deal from the lead and marks the lead as converted.
    """
    lead = await Lead.get_or_404(
        session=session,
        id=lead_id,
        company_id=user.company_id
    )

    # Update lead status
    lead.status = LeadStatusEnum.CONVERTED
    await lead.update(session=session)

    deal = None
    if create_deal:
        # Create deal from lead
        deal = await Deal.create(
            session=session,
            company_id=user.company_id,
            title=lead.title,
            contact_id=lead.contact_id,
            lead_id=lead.id,
            assigned_to=lead.assigned_to,
            amount=lead.estimated_value or 0,
            probability=50,
            description=lead.description
        )

    return {
        "success": True,
        "lead_id": str(lead.id),
        "deal_id": str(deal.id) if deal else None,
        "message": "Lead converted successfully"
    }


@router.post("/{lead_id}/assign", response_model=LeadResponse)
@require_permissions(Permissions.LEADS_ASSIGN)
async def assign_lead(
    lead_id: UUID,
    assigned_to: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Assign lead to an operator

    Only admins can assign leads.
    """
    lead = await Lead.get_or_404(
        session=session,
        id=lead_id,
        company_id=user.company_id
    )

    # Validate assignee
    assignee = await User.get_or_404(
        session=session,
        id=assigned_to,
        company_id=user.company_id
    )

    lead.assigned_to = assigned_to
    await lead.update(session=session)

    return lead
