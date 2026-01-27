"""
Contacts management endpoints

Optimized for high-load production:
- Uses subqueries instead of N+1 loops
- Batch operations for related counts
- Efficient pagination with window functions
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.contact import Contact
from db.models.lead import Lead
from db.models.deal import Deal
from db.models.call_event import CallEvent
from api.v1.schemas.crm import (
    ContactCreateRequest,
    ContactUpdateRequest,
    ContactResponse,
    PaginatedResponse
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.CONTACTS_WRITE)
async def create_contact(
    data: ContactCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new contact

    Contacts are the foundation of the CRM. They can be linked to leads, deals, and calls.
    """
    # Check for duplicates (same email in company)
    if data.email:
        existing = await Contact.get(
            email=data.email,
            company_id=user.company_id,
            session=session
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Contact with this email already exists"
            )

    contact = await Contact.create(
        session=session,
        company_id=user.company_id,
        created_by=user.id,
        **data.model_dump(exclude={'tags'})
    )

    # Add tags if provided
    if data.tags:
        # TODO: Implement tag association
        pass

    return contact


@router.get("/", response_model=PaginatedResponse)
@require_permissions(Permissions.CONTACTS_READ)
async def list_contacts(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    assigned_to: Optional[UUID] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    created_by: Optional[UUID] = None
):
    """
    List all contacts with filters and search

    OPTIMIZED: Uses subqueries for related counts instead of N+1 queries.
    Single query returns contacts with all counts.
    """
    # Base conditions
    conditions = [
        Contact.company_id == user.company_id,
        Contact.deleted_at.is_(None)
    ]

    # Search
    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                Contact.first_name.ilike(search_term),
                Contact.last_name.ilike(search_term),
                Contact.email.ilike(search_term),
                Contact.phone.ilike(search_term),
                Contact.company_name.ilike(search_term)
            )
        )

    # Filters
    if assigned_to:
        conditions.append(Contact.assigned_to == assigned_to)
    if has_email is not None:
        if has_email:
            conditions.append(Contact.email.isnot(None))
        else:
            conditions.append(Contact.email.is_(None))
    if has_phone is not None:
        if has_phone:
            conditions.append(Contact.phone.isnot(None))
        else:
            conditions.append(Contact.phone.is_(None))
    if created_by:
        conditions.append(Contact.created_by == created_by)

    # Count total (single query)
    count_query = select(func.count()).select_from(Contact).where(and_(*conditions))
    total = await session.scalar(count_query) or 0

    # Subqueries for related counts (computed in single query)
    leads_subquery = (
        select(func.count())
        .where(and_(Lead.contact_id == Contact.id, Lead.deleted_at.is_(None)))
        .correlate(Contact)
        .scalar_subquery()
    )

    deals_subquery = (
        select(func.count())
        .where(and_(Deal.contact_id == Contact.id, Deal.deleted_at.is_(None)))
        .correlate(Contact)
        .scalar_subquery()
    )

    calls_subquery = (
        select(func.count())
        .where(
            or_(
                CallEvent.phone_1 == Contact.phone,
                CallEvent.phone_2 == Contact.phone
            )
        )
        .correlate(Contact)
        .scalar_subquery()
    )

    # Main query with all counts in single database round-trip
    query = (
        select(
            Contact,
            leads_subquery.label('leads_count'),
            deals_subquery.label('deals_count'),
            calls_subquery.label('calls_count')
        )
        .where(and_(*conditions))
        .order_by(Contact.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_contacts = []
    for row in rows:
        contact = row[0]
        contact_dict = {
            "id": contact.id,
            "company_id": contact.company_id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "company_name": contact.company_name,
            "phone": contact.phone,
            "email": contact.email,
            "position": contact.position,
            "source": contact.source,
            "tags": contact.tags or [],
            "custom_fields": contact.custom_fields or {},
            "created_by": contact.created_by,
            "assigned_to": contact.assigned_to,
            "created_at": contact.created_at,
            "updated_at": contact.updated_at,
            "total_leads": row.leads_count or 0,
            "total_deals": row.deals_count or 0,
            "total_calls": row.calls_count or 0
        }
        enhanced_contacts.append(ContactResponse(**contact_dict))

    return PaginatedResponse(
        items=enhanced_contacts,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0
    )


@router.get("/{contact_id}", response_model=ContactResponse)
@require_permissions(Permissions.CONTACTS_READ)
async def get_contact(
    contact_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get contact details

    Returns full contact information with related counts (single query).
    """
    # Subqueries for related counts
    leads_subquery = (
        select(func.count())
        .where(and_(Lead.contact_id == Contact.id, Lead.deleted_at.is_(None)))
        .correlate(Contact)
        .scalar_subquery()
    )

    deals_subquery = (
        select(func.count())
        .where(and_(Deal.contact_id == Contact.id, Deal.deleted_at.is_(None)))
        .correlate(Contact)
        .scalar_subquery()
    )

    calls_subquery = (
        select(func.count())
        .where(
            or_(
                CallEvent.phone_1 == Contact.phone,
                CallEvent.phone_2 == Contact.phone
            )
        )
        .correlate(Contact)
        .scalar_subquery()
    )

    query = (
        select(
            Contact,
            leads_subquery.label('leads_count'),
            deals_subquery.label('deals_count'),
            calls_subquery.label('calls_count')
        )
        .where(
            and_(
                Contact.id == contact_id,
                Contact.company_id == user.company_id,
                Contact.deleted_at.is_(None)
            )
        )
    )

    result = await session.execute(query)
    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found"
        )

    contact = row[0]
    contact_dict = {
        "id": contact.id,
        "company_id": contact.company_id,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company_name": contact.company_name,
        "phone": contact.phone,
        "email": contact.email,
        "position": contact.position,
        "source": contact.source,
        "tags": contact.tags or [],
        "custom_fields": contact.custom_fields or {},
        "created_by": contact.created_by,
        "assigned_to": contact.assigned_to,
        "created_at": contact.created_at,
        "updated_at": contact.updated_at,
        "total_leads": row.leads_count or 0,
        "total_deals": row.deals_count or 0,
        "total_calls": row.calls_count or 0
    }

    return ContactResponse(**contact_dict)


@router.put("/{contact_id}", response_model=ContactResponse)
@require_permissions(Permissions.CONTACTS_WRITE)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update contact information

    Supports partial updates (only provided fields are updated).
    """
    contact = await Contact.get_or_404(
        session=session,
        id=contact_id,
        company_id=user.company_id
    )

    # Check email uniqueness if changing
    if data.email and data.email != contact.email:
        existing = await Contact.get(
            email=data.email,
            company_id=user.company_id,
            session=session
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Contact with this email already exists"
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True, exclude={'tags'})
    for field, value in update_data.items():
        setattr(contact, field, value)

    await contact.update(session=session)

    # Update tags if provided
    if data.tags is not None:
        # TODO: Implement tag association
        pass

    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.CONTACTS_DELETE)
async def delete_contact(
    contact_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False, description="Permanent deletion")
):
    """
    Delete a contact

    By default performs soft delete. Use hard=true for permanent deletion.
    """
    contact = await Contact.get_or_404(
        session=session,
        id=contact_id,
        company_id=user.company_id
    )

    await contact.delete(session=session, hard=hard)
    return None


@router.get("/{contact_id}/activity")
@require_permissions(Permissions.CONTACTS_READ)
async def get_contact_activity(
    contact_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get contact activity timeline

    Returns leads, deals, calls related to this contact.
    Uses optimized queries with limits.
    """
    contact = await Contact.get_or_404(
        session=session,
        id=contact_id,
        company_id=user.company_id
    )

    # Get related leads (limited)
    leads_query = (
        select(Lead)
        .where(and_(Lead.contact_id == contact.id, Lead.deleted_at.is_(None)))
        .order_by(Lead.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(leads_query)
    leads = result.scalars().all()

    # Get related deals (limited)
    deals_query = (
        select(Deal)
        .where(and_(Deal.contact_id == contact.id, Deal.deleted_at.is_(None)))
        .order_by(Deal.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(deals_query)
    deals = result.scalars().all()

    # Get related calls (limited)
    calls_query = (
        select(CallEvent)
        .where(
            or_(
                CallEvent.phone_1 == contact.phone,
                CallEvent.phone_2 == contact.phone
            )
        )
        .order_by(CallEvent.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(calls_query)
    calls = result.scalars().all()

    return {
        "contact_id": str(contact.id),
        "leads": [
            {
                "id": str(lead.id),
                "title": lead.title,
                "status": lead.status.value if lead.status else None,
                "created_at": lead.created_at.isoformat() if lead.created_at else None
            }
            for lead in leads
        ],
        "deals": [
            {
                "id": str(deal.id),
                "title": deal.title,
                "stage": deal.stage.value if deal.stage else None,
                "amount": float(deal.amount) if deal.amount else 0,
                "created_at": deal.created_at.isoformat() if deal.created_at else None
            }
            for deal in deals
        ],
        "calls": [
            {
                "id": str(call.id),
                "direction": call.direction.value if call.direction else None,
                "duration": call.billing_sec,
                "started_at": call.created_at.isoformat() if call.created_at else None
            }
            for call in calls
        ]
    }


@router.post("/bulk", response_model=List[ContactResponse], status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.CONTACTS_WRITE)
async def bulk_create_contacts(
    contacts: List[ContactCreateRequest],
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Bulk create contacts

    Efficiently creates multiple contacts in a single transaction.
    Maximum 100 contacts per request.
    """
    if len(contacts) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 contacts per bulk request"
        )

    created_contacts = []
    for contact_data in contacts:
        contact = Contact(
            company_id=user.company_id,
            created_by=user.id,
            **contact_data.model_dump(exclude={'tags'})
        )
        session.add(contact)
        created_contacts.append(contact)

    await session.flush()

    for contact in created_contacts:
        await session.refresh(contact)

    await session.commit()

    return created_contacts
