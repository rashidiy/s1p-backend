"""
Notes management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.note import Note
from api.v1.schemas.crm import (
    NoteCreateRequest,
    NoteUpdateRequest,
    NoteResponse,
    PaginatedResponse
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.NOTES_WRITE)
async def create_note(
    data: NoteCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new note

    Notes can be attached to contacts, leads, deals, tasks, or calls.
    """
    note = await Note.create(
        session=session,
        company_id=user.company_id,
        created_by=user.id,
        **data.model_dump()
    )

    return note


@router.get("", response_model=PaginatedResponse)
@require_permissions(Permissions.NOTES_READ)
async def list_notes(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    contact_id: Optional[UUID] = None,
    lead_id: Optional[UUID] = None,
    deal_id: Optional[UUID] = None,
    task_id: Optional[UUID] = None,
    call_id: Optional[int] = None,
    created_by: Optional[UUID] = None
):
    """
    List all notes with filters

    Can filter by entity (contact, lead, deal, task, call) or creator.
    """
    query = select(Note).where(
        Note.company_id == user.company_id,
        Note.deleted_at.is_(None)
    )

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.where(Note.content.ilike(search_term))

    # Filters
    if contact_id:
        query = query.where(Note.entity_type == "contact", Note.entity_id == str(contact_id))
    if lead_id:
        query = query.where(Note.entity_type == "lead", Note.entity_id == str(lead_id))
    if deal_id:
        query = query.where(Note.entity_type == "deal", Note.entity_id == str(deal_id))
    if task_id:
        query = query.where(Note.entity_type == "task", Note.entity_id == str(task_id))
    if call_id:
        query = query.where(Note.entity_type == "call", Note.entity_id == str(call_id))
    if created_by:
        query = query.where(Note.created_by == created_by)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Subquery for creator name (avoids N+1 queries)
    creator_name_subquery = (
        select(func.trim(func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))))
        .where(User.id == Note.created_by)
        .correlate(Note)
        .scalar_subquery()
    )

    # Paginate with name subquery
    query = query.add_columns(creator_name_subquery.label('created_by_name'))
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Note.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_notes = []
    for row in rows:
        note = row[0]
        note_dict = {
            **{k: v for k, v in note.__dict__.items() if not k.startswith('_')},
            "created_by_name": row.created_by_name
        }
        enhanced_notes.append(NoteResponse(**note_dict))

    return PaginatedResponse(
        items=enhanced_notes,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/{note_id}", response_model=NoteResponse)
@require_permissions(Permissions.NOTES_READ)
async def get_note(
    note_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """Get note details"""
    note = await Note.get_or_404(
        session=session,
        id=note_id,
        company_id=user.company_id
    )

    creator_name = None
    if note.created_by:
        creator = await User.get(session=session, id=note.created_by)
        if creator:
            creator_name = creator.full_name

    note_dict = {
        **{k: v for k, v in note.__dict__.items() if not k.startswith('_')},
        "created_by_name": creator_name
    }

    return NoteResponse(**note_dict)


@router.put("/{note_id}", response_model=NoteResponse)
@require_permissions(Permissions.NOTES_WRITE)
async def update_note(
    note_id: UUID,
    data: NoteUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update note content

    Users can only update their own notes (unless admin).
    """
    note = await Note.get_or_404(
        session=session,
        id=note_id,
        company_id=user.company_id
    )

    # Check permissions: users can only update their own notes
    from db.models.enums import RoleEnum
    if user.role not in [RoleEnum.OWNER, RoleEnum.COMPANY_ADMIN] and note.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own notes"
        )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await note.update(session=session)

    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.NOTES_DELETE)
async def delete_note(
    note_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = Query(False)
):
    """
    Delete a note

    Users can only delete their own notes (unless admin).
    """
    note = await Note.get_or_404(
        session=session,
        id=note_id,
        company_id=user.company_id
    )

    # Check permissions: users can only delete their own notes
    from db.models.enums import RoleEnum
    if user.role not in [RoleEnum.OWNER, RoleEnum.COMPANY_ADMIN] and note.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own notes"
        )

    await note.delete(session=session, hard=hard)
    return None


@router.get("/timeline/{entity_type}/{entity_id}")
@require_permissions(Permissions.NOTES_READ)
async def get_entity_notes(
    entity_type: str,
    entity_id: str,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get all notes for an entity

    entity_type: contact, lead, deal, task, call
    Returns notes in chronological order.
    """
    query = select(Note).where(
        Note.company_id == user.company_id,
        Note.deleted_at.is_(None)
    )

    valid_entity_types = {"contact", "lead", "deal", "task", "call"}
    if entity_type not in valid_entity_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entity_type. Must be: contact, lead, deal, task, or call"
        )

    query = query.where(Note.entity_type == entity_type, Note.entity_id == entity_id)

    # Subquery for creator name (avoids N+1 queries)
    creator_name_subquery = (
        select(func.trim(func.concat(User.first_name, ' ', func.coalesce(User.last_name, ''))))
        .where(User.id == Note.created_by)
        .correlate(Note)
        .scalar_subquery()
    )

    query = query.add_columns(creator_name_subquery.label('created_by_name'))
    query = query.order_by(Note.created_at.desc())

    result = await session.execute(query)
    rows = result.all()

    # Build response
    enhanced_notes = []
    for row in rows:
        note = row[0]
        enhanced_notes.append({
            "id": str(note.id),
            "content": note.content,
            "created_by": str(note.created_by) if note.created_by else None,
            "created_by_name": row.created_by_name,
            "created_at": note.created_at.isoformat()
        })

    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "notes": enhanced_notes,
        "total": len(enhanced_notes)
    }
