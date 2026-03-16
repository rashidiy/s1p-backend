"""
Custom field definitions management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.custom_field import CustomFieldDefinition
from db.models.enums import CustomFieldTypeEnum
from api.v1.schemas.custom_field import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionUpdate,
    CustomFieldDefinitionResponse,
    CustomFieldReorderRequest,
    VALID_ENTITY_TYPES,
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])

MAX_FIELDS_PER_ENTITY = 20


@router.post("", response_model=CustomFieldDefinitionResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_custom_field_definition(
    data: CustomFieldDefinitionCreate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a custom field definition.

    Maximum 20 custom fields per entity type per company.
    """
    # Check limit
    count_query = select(func.count()).select_from(CustomFieldDefinition).where(
        and_(
            CustomFieldDefinition.company_id == user.company_id,
            CustomFieldDefinition.entity_type == data.entity_type,
            CustomFieldDefinition.deleted_at.is_(None)
        )
    )
    count = await session.scalar(count_query) or 0
    if count >= MAX_FIELDS_PER_ENTITY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_FIELDS_PER_ENTITY} custom fields per entity type"
        )

    # Check uniqueness
    existing = await CustomFieldDefinition.get(
        session=session,
        company_id=user.company_id,
        entity_type=data.entity_type,
        field_name=data.field_name,
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Custom field '{data.field_name}' already exists for {data.entity_type}"
        )

    # Validate dropdown options
    if data.field_type == "dropdown" and not data.options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dropdown fields must have at least one option"
        )

    definition = await CustomFieldDefinition.create(
        session=session,
        company_id=user.company_id,
        entity_type=data.entity_type,
        field_name=data.field_name,
        field_type=CustomFieldTypeEnum(data.field_type),
        options=data.options,
        sort_order=data.sort_order,
        is_required=data.is_required,
    )

    return definition


@router.get("", response_model=List[CustomFieldDefinitionResponse])
@require_permissions(Permissions.SETTINGS_READ)
async def list_custom_field_definitions(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
):
    """
    List custom field definitions for the company.

    Optionally filter by entity_type.
    """
    conditions = [
        CustomFieldDefinition.company_id == user.company_id,
        CustomFieldDefinition.deleted_at.is_(None),
    ]

    if entity_type:
        if entity_type not in VALID_ENTITY_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"entity_type must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}"
            )
        conditions.append(CustomFieldDefinition.entity_type == entity_type)

    query = (
        select(CustomFieldDefinition)
        .where(and_(*conditions))
        .order_by(CustomFieldDefinition.entity_type, CustomFieldDefinition.sort_order)
    )

    result = await session.execute(query)
    return result.scalars().all()


# Reorder must be before /{definition_id} to avoid route conflict
@router.put("/reorder", response_model=List[CustomFieldDefinitionResponse])
@require_permissions(Permissions.SETTINGS_MANAGE)
async def reorder_custom_field_definitions(
    data: CustomFieldReorderRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Reorder custom field definitions.

    Provide an ordered list of field definition IDs.
    """
    for idx, field_id in enumerate(data.field_ids):
        definition = await CustomFieldDefinition.get(
            session=session,
            id=field_id,
            company_id=user.company_id,
        )
        if not definition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Custom field definition {field_id} not found"
            )
        definition.sort_order = idx
        await session.flush()

    await session.commit()

    # Return reordered list
    query = (
        select(CustomFieldDefinition)
        .where(
            and_(
                CustomFieldDefinition.id.in_(data.field_ids),
                CustomFieldDefinition.company_id == user.company_id,
                CustomFieldDefinition.deleted_at.is_(None),
            )
        )
        .order_by(CustomFieldDefinition.sort_order)
    )
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/{definition_id}", response_model=CustomFieldDefinitionResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_custom_field_definition(
    definition_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get a single custom field definition

    Returns field name, type, options, and sort order.
    """
    definition = await CustomFieldDefinition.get_or_404(
        session=session,
        id=definition_id,
        company_id=user.company_id,
    )
    return definition


@router.put("/{definition_id}", response_model=CustomFieldDefinitionResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_custom_field_definition(
    definition_id: UUID,
    data: CustomFieldDefinitionUpdate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update a custom field definition.

    Note: field_type cannot be changed after creation.
    """
    definition = await CustomFieldDefinition.get_or_404(
        session=session,
        id=definition_id,
        company_id=user.company_id,
    )

    update_data = data.model_dump(exclude_unset=True)

    # Check field_name uniqueness if changing
    if "field_name" in update_data and update_data["field_name"] != definition.field_name:
        existing = await CustomFieldDefinition.get(
            session=session,
            company_id=user.company_id,
            entity_type=definition.entity_type,
            field_name=update_data["field_name"],
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Custom field '{update_data['field_name']}' already exists for {definition.entity_type}"
            )

    for field, value in update_data.items():
        setattr(definition, field, value)

    await definition.update(session=session)
    return definition


@router.delete("/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_custom_field_definition(
    definition_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a custom field definition

    Soft deletes the definition. Existing field values on entities are preserved
    but no longer visible in the UI. Requires SETTINGS_MANAGE permission.
    """
    definition = await CustomFieldDefinition.get_or_404(
        session=session,
        id=definition_id,
        company_id=user.company_id,
    )

    await definition.delete(session=session)
    return None
