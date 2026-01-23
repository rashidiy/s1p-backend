"""
Contacts management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
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
    user: User = Depends(User.current),
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
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    has_email: Optional[bool] = None,
    has_phone: Optional[bool] = None,
    created_by: Optional[UUID] = None
):
    """
    List all contacts with filters and search

    Supports pagination, search by name/email/phone, and filtering.
    """
    query = select(Contact).where(Contact.company_id == user.company_id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Contact.first_name.ilike(search_term),
                Contact.last_name.ilike(search_term),
                Contact.email.ilike(search_term),
                Contact.phone.ilike(search_term),
                Contact.company_name.ilike(search_term)
            )
        )

    # Filters
    if city:
        query = query.where(Contact.city == city)
    if country:
        query = query.where(Contact.country == country)
    if has_email is not None:
        if has_email:
            query = query.where(Contact.email.isnot(None))
        else:
            query = query.where(Contact.email.is_(None))
    if has_phone is not None:
        if has_phone:
            query = query.where(Contact.phone.isnot(None))
        else:
            query = query.where(Contact.phone.is_(None))
    if created_by:
        query = query.where(Contact.created_by == created_by)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Contact.created_at.desc())

    result = await session.execute(query)
    contacts = result.scalars().all()

    # Enhance with related counts
    enhanced_contacts = []
    for contact in contacts:
        # Get related counts
        leads_count = await session.scalar(
            select(func.count()).select_from(Lead).where(Lead.contact_id == contact.id)
        ) or 0
        deals_count = await session.scalar(
            select(func.count()).select_from(Deal).where(Deal.contact_id == contact.id)
        ) or 0
        calls_count = await session.scalar(
            select(func.count()).select_from(CallEvent).where(
                or_(
                    CallEvent.phone_1 == contact.phone,
                    CallEvent.phone_2 == contact.phone
                )
            )
        ) or 0

        contact_dict = {
            **{k: v for k, v in contact.__dict__.items() if not k.startswith('_')},
            "total_leads": leads_count,
            "total_deals": deals_count,
            "total_calls": calls_count
        }
        enhanced_contacts.append(ContactResponse(**contact_dict))

    return PaginatedResponse(
        items=enhanced_contacts,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{contact_id}", response_model=ContactResponse)
@require_permissions(Permissions.CONTACTS_READ)
async def get_contact(
    contact_id: UUID,
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get contact details

    Returns full contact information with related counts.
    """
    contact = await Contact.get_or_404(
        session=session,
        id=contact_id,
        company_id=user.company_id
    )

    # Get related counts
    leads_count = await session.scalar(
        select(func.count()).select_from(Lead).where(Lead.contact_id == contact.id)
    ) or 0
    deals_count = await session.scalar(
        select(func.count()).select_from(Deal).where(Deal.contact_id == contact.id)
    ) or 0
    calls_count = await session.scalar(
        select(func.count()).select_from(CallEvent).where(
            or_(
                CallEvent.phone_1 == contact.phone,
                CallEvent.phone_2 == contact.phone
            )
        )
    ) or 0

    contact_dict = {
        **{k: v for k, v in contact.__dict__.items() if not k.startswith('_')},
        "total_leads": leads_count,
        "total_deals": deals_count,
        "total_calls": calls_count
    }

    return ContactResponse(**contact_dict)


@router.put("/{contact_id}", response_model=ContactResponse)
@require_permissions(Permissions.CONTACTS_WRITE)
async def update_contact(
    contact_id: UUID,
    data: ContactUpdateRequest,
    user: User = Depends(User.current),
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
    user: User = Depends(User.current),
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
    user: User = Depends(User.current),
    session: AsyncSession = Depends(get_session)
):
    """
    Get contact activity timeline

    Returns leads, deals, calls, and tasks related to this contact.
    """
    contact = await Contact.get_or_404(
        session=session,
        id=contact_id,
        company_id=user.company_id
    )

    # Get related leads
    leads_query = select(Lead).where(Lead.contact_id == contact.id).order_by(Lead.created_at.desc())
    result = await session.execute(leads_query)
    leads = result.scalars().all()

    # Get related deals
    deals_query = select(Deal).where(Deal.contact_id == contact.id).order_by(Deal.created_at.desc())
    result = await session.execute(deals_query)
    deals = result.scalars().all()

    # Get related calls
    calls_query = select(CallEvent).where(
        or_(
            CallEvent.phone_1 == contact.phone,
            CallEvent.phone_2 == contact.phone
        )
    ).order_by(CallEvent.started_at.desc())
    result = await session.execute(calls_query)
    calls = result.scalars().all()

    return {
        "contact_id": str(contact.id),
        "leads": [
            {
                "id": str(lead.id),
                "title": lead.title,
                "status": lead.status.value if lead.status else None,
                "created_at": lead.created_at.isoformat()
            }
            for lead in leads
        ],
        "deals": [
            {
                "id": str(deal.id),
                "title": deal.title,
                "stage": deal.stage.value if deal.stage else None,
                "value": deal.value,
                "created_at": deal.created_at.isoformat()
            }
            for deal in deals
        ],
        "calls": [
            {
                "id": str(call.id),
                "direction": call.direction.value if call.direction else None,
                "duration": call.duration,
                "started_at": call.started_at.isoformat() if call.started_at else None
            }
            for call in calls[:20]  # Last 20 calls
        ]
    }
