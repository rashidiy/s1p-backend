"""
Custom field definition management endpoints

Admin-only CRUD for custom field definitions.
All endpoints are company-scoped via JWT.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.custom_field import CustomFieldDefinition
from api.v1.schemas.custom_field import (
    CustomFieldCreate,
    CustomFieldUpdate,
    CustomFieldResponse,
    CustomFieldListResponse,
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])

MAX_FIELDS_PER_ENTITY = 20


@router.get("", response_model=CustomFieldListResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def list_custom_fields(
    entity_type: str = Query(
        ...,
        description="Entity type to list fields for: contact, lead, deal, task",
    ),
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    List custom field definitions for a given entity type.

    Scoped to the current user's company.
    """
    query = (
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.company_id == user.company_id,
            CustomFieldDefinition.entity_type == entity_type.lower().strip(),
            CustomFieldDefinition.deleted_at.is_(None),
        )
        .order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.created_at)
    )

    result = await session.execute(query)
    fields = result.scalars().all()

    return CustomFieldListResponse(fields=fields, total=len(fields))


@router.post("", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_custom_field(
    data: CustomFieldCreate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a custom field definition.

    Admin only. Max 20 fields per entity_type per company.
    """
    # Enforce limit: max 20 per entity_type per company
    count_query = (
        select(func.count())
        .select_from(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.company_id == user.company_id,
            CustomFieldDefinition.entity_type == data.entity_type,
            CustomFieldDefinition.deleted_at.is_(None),
        )
    )
    result = await session.execute(count_query)
    current_count = result.scalar_one()

    if current_count >= MAX_FIELDS_PER_ENTITY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum of {MAX_FIELDS_PER_ENTITY} custom fields per entity type reached",
        )

    # Check name uniqueness within company + entity_type
    existing = await CustomFieldDefinition.get(
        session=session,
        company_id=user.company_id,
        entity_type=data.entity_type,
        field_name=data.field_name,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A custom field named '{data.field_name}' already exists for entity type '{data.entity_type}'",
        )

    field = await CustomFieldDefinition.create(
        session=session,
        company_id=user.company_id,
        entity_type=data.entity_type,
        field_name=data.field_name,
        field_type=data.field_type,
        options=data.options,
        required=data.required,
        sort_order=data.sort_order,
    )

    return field


@router.put("/{field_id}", response_model=CustomFieldResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_custom_field(
    field_id: UUID,
    data: CustomFieldUpdate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Update a custom field definition.

    Admin only. Cannot change field_type after creation.
    """
    field = await CustomFieldDefinition.get(
        session=session,
        id=field_id,
        company_id=user.company_id,
    )
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom field definition not found",
        )

    # Update field_name if provided
    if data.field_name is not None:
        # Check uniqueness of new name
        existing = await CustomFieldDefinition.get(
            session=session,
            company_id=user.company_id,
            entity_type=field.entity_type,
            field_name=data.field_name,
        )
        if existing and existing.id != field.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A custom field named '{data.field_name}' already exists for entity type '{field.entity_type}'",
            )
        field.field_name = data.field_name

    # Update options (only meaningful for dropdown, but store if provided)
    if data.options is not None:
        if field.field_type == "dropdown":
            if len(data.options) == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Dropdown fields must have at least one option",
                )
            for opt in data.options:
                if not isinstance(opt, str) or not opt.strip():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Each dropdown option must be a non-empty string",
                    )
        field.options = data.options

    if data.required is not None:
        field.required = data.required

    if data.sort_order is not None:
        field.sort_order = data.sort_order

    await field.update(session=session)
    return field


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_custom_field(
    field_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Soft-delete a custom field definition.

    Admin only. Does not remove existing values from entity custom_fields JSONB.
    """
    field = await CustomFieldDefinition.get(
        session=session,
        id=field_id,
        company_id=user.company_id,
    )
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom field definition not found",
        )

    await field.delete(session=session)
    return None
