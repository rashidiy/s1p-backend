"""
Custom field value validation utility

Validates custom_fields values dict against CustomFieldDefinition list.
"""

import re
from typing import Any

from fastapi import HTTPException, status

from db.models.custom_field import CustomFieldDefinition


# ISO date pattern: YYYY-MM-DD
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_custom_field_values(
    values: dict[str, Any],
    definitions: list[CustomFieldDefinition],
) -> dict[str, Any]:
    """
    Validate custom field values against their definitions.

    Args:
        values: Dict of {field_name: value} submitted by the client.
        definitions: List of CustomFieldDefinition objects for the entity type.

    Returns:
        Cleaned dict of validated values.

    Raises:
        HTTPException 422 with detailed error messages on validation failure.
    """
    errors: list[str] = []
    clean: dict[str, Any] = {}

    # Build lookup by field_name
    defs_by_name: dict[str, CustomFieldDefinition] = {
        d.field_name: d for d in definitions if d.deleted_at is None
    }

    # Check required fields are present
    for field_name, defn in defs_by_name.items():
        if defn.required and field_name not in values:
            errors.append(f"Required custom field '{field_name}' is missing")

    # Validate provided values
    for field_name, value in values.items():
        defn = defs_by_name.get(field_name)
        if defn is None:
            errors.append(f"Unknown custom field '{field_name}'")
            continue

        # Allow None for non-required fields
        if value is None:
            if defn.required:
                errors.append(f"Required custom field '{field_name}' cannot be null")
            else:
                clean[field_name] = None
            continue

        field_type = defn.field_type

        if field_type == "text":
            if not isinstance(value, str):
                errors.append(
                    f"Custom field '{field_name}' must be a string (got {type(value).__name__})"
                )
            else:
                clean[field_name] = value

        elif field_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(
                    f"Custom field '{field_name}' must be a number (got {type(value).__name__})"
                )
            else:
                clean[field_name] = value

        elif field_type == "dropdown":
            if not isinstance(value, str):
                errors.append(
                    f"Custom field '{field_name}' must be a string (got {type(value).__name__})"
                )
            elif defn.options and value not in defn.options:
                errors.append(
                    f"Custom field '{field_name}' value '{value}' is not in allowed options: {defn.options}"
                )
            else:
                clean[field_name] = value

        elif field_type == "date":
            if not isinstance(value, str):
                errors.append(
                    f"Custom field '{field_name}' must be an ISO date string YYYY-MM-DD (got {type(value).__name__})"
                )
            elif not ISO_DATE_PATTERN.match(value):
                errors.append(
                    f"Custom field '{field_name}' must be an ISO date string YYYY-MM-DD (got '{value}')"
                )
            else:
                clean[field_name] = value

        elif field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(
                    f"Custom field '{field_name}' must be a boolean (got {type(value).__name__})"
                )
            else:
                clean[field_name] = value

        else:
            errors.append(
                f"Custom field '{field_name}' has unsupported type '{field_type}'"
            )

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"custom_field_errors": errors},
        )

    return clean
