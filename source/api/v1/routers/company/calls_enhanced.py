"""
Enhanced call management with outcomes and CRM linking
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, case, literal
from typing import Optional
from uuid import UUID
from datetime import datetime, date

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.deal import Deal
from db.models.enums import CallOutcomeEnum, CallDirectionEnum, RoleEnum
from api.v1.schemas.crm import PaginatedResponse
from utils.permissions import require_permissions, Permissions
from pydantic import BaseModel, Field

router = APIRouter(prefix="/calls", tags=["Calls - Enhanced"])


# Schemas
class CallOutcomeUpdate(BaseModel):
    """Update call outcome"""
    outcome: str = Field(..., description="Call outcome")
    disposition_notes: Optional[str] = Field(None, max_length=5000, description="Notes about the call")


class CallLinkRequest(BaseModel):
    """Link call to CRM entities"""
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None


class CallWithDetails(BaseModel):
    """Call event with CRM details"""
    id: int
    phone_1: Optional[str]
    phone_2: Optional[str]
    direction: Optional[str]
    state: Optional[str]
    duration: Optional[int]
    outcome: Optional[str]
    disposition_notes: Optional[str]
    started_at: Optional[datetime]

    # CRM links
    contact_id: Optional[UUID]
    contact_name: Optional[str]
    lead_id: Optional[UUID]
    lead_title: Optional[str]
    deal_id: Optional[UUID]
    deal_title: Optional[str]

    operator_id: Optional[UUID]
    operator_name: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True


# Endpoints

@router.put("/{call_id}/outcome")
@require_permissions(Permissions.CALLS_WRITE)
async def set_call_outcome(
    call_id: int,
    data: CallOutcomeUpdate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Set call outcome/disposition

    Operators can set outcomes for calls to track results.
    """
    call = await CallEvent.get_or_404(
        session=session,
        id=call_id,
        company_id=user.company_id
    )

    # Validate outcome
    try:
        outcome_enum = CallOutcomeEnum(data.outcome)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid outcome. Must be one of: {[o.value for o in CallOutcomeEnum]}"
        )

    call.outcome = outcome_enum
    call.disposition_notes = data.disposition_notes

    await call.update(session=session)

    return {"success": True, "message": "Call outcome updated"}


@router.post("/{call_id}/link")
@require_permissions(Permissions.CALLS_WRITE)
async def link_call_to_crm(
    call_id: int,
    data: CallLinkRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Link call to CRM entities (contact, lead, deal)

    Associates a call with CRM records for tracking and reporting.
    """
    call = await CallEvent.get_or_404(
        session=session,
        id=call_id,
        company_id=user.company_id
    )

    # Validate and link contact
    if data.contact_id:
        contact = await Contact.get_or_404(
            session=session,
            id=data.contact_id,
            company_id=user.company_id
        )
        call.contact_id = contact.id

    # Validate and link lead
    if data.lead_id:
        lead = await Lead.get_or_404(
            session=session,
            id=data.lead_id,
            company_id=user.company_id
        )
        call.lead_id = lead.id

    # Validate and link deal
    if data.deal_id:
        deal = await Deal.get_or_404(
            session=session,
            id=data.deal_id,
            company_id=user.company_id
        )
        call.deal_id = deal.id

    await call.update(session=session)

    return {
        "success": True,
        "message": "Call linked to CRM entities",
        "links": {
            "contact_id": str(call.contact_id) if call.contact_id else None,
            "lead_id": str(call.lead_id) if call.lead_id else None,
            "deal_id": str(call.deal_id) if call.deal_id else None
        }
    }


@router.get("/history", response_model=PaginatedResponse)
@require_permissions(Permissions.CALLS_READ)
async def get_call_history(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    direction: Optional[str] = None,
    outcome: Optional[str] = None,
    operator_id: Optional[UUID] = None,
    contact_id: Optional[UUID] = None,
    lead_id: Optional[UUID] = None,
    deal_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    my_calls: bool = Query(False, description="Show only my calls")
):
    """
    Enhanced call history with comprehensive filters

    Operators only see their own calls. Admins and Managers see all company calls.
    """
    query = select(CallEvent).where(CallEvent.company_id == user.company_id)

    # Operator scoping: operators only see their own calls
    if user.role == RoleEnum.COMPANY_OPERATOR:
        query = query.where(CallEvent.operator_id == user.id)
    elif my_calls:
        query = query.where(CallEvent.operator_id == user.id)

    # Search by phone number
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                CallEvent.phone_1.ilike(search_term),
                CallEvent.phone_2.ilike(search_term)
            )
        )

    # Filters
    if direction:
        try:
            direction_enum = CallDirectionEnum(direction)
            query = query.where(CallEvent.direction == direction_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid direction. Must be one of: {[d.value for d in CallDirectionEnum]}"
            )

    if outcome:
        try:
            outcome_enum = CallOutcomeEnum(outcome)
            query = query.where(CallEvent.outcome == outcome_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid outcome. Must be one of: {[o.value for o in CallOutcomeEnum]}"
            )

    if operator_id:
        query = query.where(CallEvent.operator_id == operator_id)
    if contact_id:
        query = query.where(CallEvent.contact_id == contact_id)
    if lead_id:
        query = query.where(CallEvent.lead_id == lead_id)
    if deal_id:
        query = query.where(CallEvent.deal_id == deal_id)

    # Date range
    if date_from:
        query = query.where(func.date(CallEvent.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(CallEvent.created_at) <= date_to)

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
        .where(Contact.id == CallEvent.contact_id)
        .correlate(CallEvent)
        .scalar_subquery()
    )
    lead_title_subquery = (
        select(Lead.title)
        .where(and_(Lead.id == CallEvent.lead_id, Lead.deleted_at.is_(None)))
        .correlate(CallEvent)
        .scalar_subquery()
    )
    deal_title_subquery = (
        select(Deal.title)
        .where(and_(Deal.id == CallEvent.deal_id, Deal.deleted_at.is_(None)))
        .correlate(CallEvent)
        .scalar_subquery()
    )
    operator_name_subquery = (
        select(func.trim(func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))))
        .where(User.id == CallEvent.operator_id)
        .correlate(CallEvent)
        .scalar_subquery()
    )

    # Paginate with name subqueries
    query = query.add_columns(
        contact_name_subquery.label('contact_name'),
        lead_title_subquery.label('lead_title'),
        deal_title_subquery.label('deal_title'),
        operator_name_subquery.label('operator_name'),
    )
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(CallEvent.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_calls = []
    for row in rows:
        call = row[0]
        call_dict = {
            "id": call.id,
            "phone_1": call.phone_1,
            "phone_2": call.phone_2,
            "direction": call.direction.value if call.direction else None,
            "state": call.state.value if call.state else None,
            "duration": call.billing_sec,
            "outcome": call.outcome.value if call.outcome else None,
            "disposition_notes": call.disposition_notes,
            "started_at": call.call_start_timestamp,
            "contact_id": call.contact_id,
            "contact_name": row.contact_name,
            "lead_id": call.lead_id,
            "lead_title": row.lead_title,
            "deal_id": call.deal_id,
            "deal_title": row.deal_title,
            "operator_id": call.operator_id,
            "operator_name": row.operator_name,
            "created_at": call.created_at
        }
        enhanced_calls.append(CallWithDetails(**call_dict))

    return PaginatedResponse(
        items=enhanced_calls,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/outcomes/summary")
@require_permissions(Permissions.CALLS_READ)
async def get_call_outcomes_summary(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    operator_id: Optional[UUID] = None
):
    """
    Get call outcomes summary statistics

    Returns counts and percentages for each outcome type.
    """
    query = select(CallEvent).where(CallEvent.company_id == user.company_id)

    # Operators only see their own call stats
    if user.role == RoleEnum.COMPANY_OPERATOR:
        query = query.where(CallEvent.operator_id == user.id)
    elif operator_id:
        query = query.where(CallEvent.operator_id == operator_id)

    if date_from:
        query = query.where(func.date(CallEvent.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(CallEvent.created_at) <= date_to)

    result = await session.execute(query)
    calls = result.scalars().all()

    total_calls = len(calls)
    if total_calls == 0:
        return {
            "total_calls": 0,
            "by_outcome": {},
            "date_from": date_from,
            "date_to": date_to
        }

    # Group by outcome
    by_outcome = {}
    calls_with_outcome = [c for c in calls if c.outcome]

    for outcome in CallOutcomeEnum:
        count = sum(1 for c in calls_with_outcome if c.outcome == outcome)
        percentage = (count / len(calls_with_outcome) * 100) if calls_with_outcome else 0

        by_outcome[outcome.value] = {
            "count": count,
            "percentage": round(percentage, 2)
        }

    # Add stats for calls without outcome
    no_outcome_count = total_calls - len(calls_with_outcome)
    no_outcome_percentage = (no_outcome_count / total_calls * 100) if total_calls else 0

    return {
        "total_calls": total_calls,
        "calls_with_outcome": len(calls_with_outcome),
        "calls_without_outcome": no_outcome_count,
        "no_outcome_percentage": round(no_outcome_percentage, 2),
        "by_outcome": by_outcome,
        "date_from": date_from,
        "date_to": date_to
    }


@router.get("/auto-link-suggestions/{phone_number}")
@require_permissions(Permissions.CALLS_READ)
async def get_auto_link_suggestions(
    phone_number: str,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get suggestions for linking a call to CRM entities

    Searches for contacts, leads, and deals that match the phone number.
    """
    # Search for contacts with this phone number
    contacts_query = select(Contact).where(
        and_(
            Contact.company_id == user.company_id,
            Contact.deleted_at.is_(None),
            Contact.phone == phone_number
        )
    )
    result = await session.execute(contacts_query)
    contacts = result.scalars().all()

    suggestions = {
        "phone_number": phone_number,
        "contacts": [],
        "leads": [],
        "deals": []
    }

    # Add contact suggestions
    for contact in contacts:
        suggestions["contacts"].append({
            "id": str(contact.id),
            "name": f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Unknown",
            "email": contact.email,
            "company": contact.company_name
        })

        # Get leads for this contact
        if contact.id:
            leads_query = select(Lead).where(Lead.contact_id == contact.id, Lead.deleted_at.is_(None))
            result = await session.execute(leads_query)
            leads = result.scalars().all()

            for lead in leads:
                suggestions["leads"].append({
                    "id": str(lead.id),
                    "title": lead.title,
                    "status": lead.status.value if lead.status else None,
                    "contact_id": str(contact.id)
                })

            # Get deals for this contact
            deals_query = select(Deal).where(Deal.contact_id == contact.id, Deal.deleted_at.is_(None))
            result = await session.execute(deals_query)
            deals = result.scalars().all()

            for deal in deals:
                suggestions["deals"].append({
                    "id": str(deal.id),
                    "title": deal.title,
                    "stage": deal.stage.value if deal.stage else None,
                    "value": float(deal.amount) if deal.amount else None,
                    "contact_id": str(contact.id)
                })

    return suggestions
