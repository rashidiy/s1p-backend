"""
Custom field value validation against field definitions
"""

from typing import Dict, Any, List, Optional
from datetime import date, datetime
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_


def validate_custom_field_values(
    values: Dict[str, Any],
    definitions: List,
    partial: bool = False
) -> Dict[str, Any]:
    """
    Validate custom field values against their definitions.

    Args:
        values: Dict of field_name -> value to validate
        definitions: List of CustomFieldDefinition objects
        partial: If True, skip required field checks (for partial updates)

    Returns:
        Validated values dict

    Raises:
        HTTPException 422 on validation errors
    """
    if not values:
        if not partial:
            # Check required fields
            required_fields = [d for d in definitions if d.is_required]
            if required_fields:
                missing = [d.field_name for d in required_fields]
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Missing required custom fields: {', '.join(missing)}"
                )
        return values or {}

    defs_by_name = {d.field_name: d for d in definitions}
    errors = []

    # Check for unknown fields
    unknown = set(values.keys()) - set(defs_by_name.keys())
    if unknown:
        errors.append(f"Unknown custom fields: {', '.join(sorted(unknown))}")

    # Validate each provided value
    for field_name, value in values.items():
        if field_name not in defs_by_name:
            continue

        definition = defs_by_name[field_name]

        # Allow null values for non-required fields
        if value is None:
            if definition.is_required:
                errors.append(f"Field '{field_name}' is required and cannot be null")
            continue

        field_type = definition.field_type
        if hasattr(field_type, 'value'):
            field_type = field_type.value

        if field_type == "text":
            if not isinstance(value, str):
                errors.append(f"Field '{field_name}' must be a string")

        elif field_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"Field '{field_name}' must be a number")

        elif field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Field '{field_name}' must be a boolean")

        elif field_type == "date":
            if not isinstance(value, str):
                errors.append(f"Field '{field_name}' must be a date string (YYYY-MM-DD)")
            else:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    errors.append(f"Field '{field_name}' must be a valid date (YYYY-MM-DD)")

        elif field_type == "dropdown":
            options = definition.options or []
            if value not in options:
                errors.append(
                    f"Field '{field_name}' value '{value}' is not in allowed options: {options}"
                )

    # Check required fields not provided
    if not partial:
        for definition in definitions:
            if definition.is_required and definition.field_name not in values:
                errors.append(f"Required custom field '{definition.field_name}' is missing")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"custom_field_errors": errors}
        )

    return values


async def validate_entity_custom_fields(
    session: AsyncSession,
    company_id: UUID,
    entity_type: str,
    custom_fields: Optional[Dict[str, Any]],
    partial: bool = False,
) -> None:
    """
    Fetch definitions for an entity type and validate custom field values.

    Call this from entity create/update endpoints.
    """
    from db.models.custom_field_definition import CustomFieldDefinition

    query = (
        select(CustomFieldDefinition)
        .where(
            and_(
                CustomFieldDefinition.company_id == company_id,
                CustomFieldDefinition.entity_type == entity_type,
                CustomFieldDefinition.deleted_at.is_(None),
            )
        )
    )
    result = await session.execute(query)
    definitions = result.scalars().all()

    if not definitions and not custom_fields:
        return

    if definitions:
        validate_custom_field_values(
            values=custom_fields or {},
            definitions=definitions,
            partial=partial,
        )
