"""
Custom field definition schemas
"""

import re
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator


VALID_ENTITY_TYPES = {"contact", "lead", "deal", "task"}
VALID_FIELD_TYPES = {"text", "number", "dropdown", "date", "boolean"}
FIELD_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


class CustomFieldCreate(BaseModel):
    """Create a custom field definition"""

    entity_type: str = Field(
        ...,
        description="Entity type: contact, lead, deal, or task",
    )
    field_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Field name (alphanumeric + underscore only)",
    )
    field_type: str = Field(
        ...,
        description="Field type: text, number, dropdown, date, or boolean",
    )
    options: Optional[List[str]] = Field(
        None,
        description="Dropdown choices (required if field_type is dropdown)",
    )
    required: bool = Field(False, description="Whether this field is required")
    sort_order: int = Field(0, description="Display order")

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type '{v}'. Must be one of: {sorted(VALID_ENTITY_TYPES)}"
            )
        return v

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        v = v.strip()
        if not FIELD_NAME_PATTERN.match(v):
            raise ValueError(
                "field_name must contain only alphanumeric characters and underscores"
            )
        return v

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_FIELD_TYPES:
            raise ValueError(
                f"Invalid field_type '{v}'. Must be one of: {sorted(VALID_FIELD_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_dropdown_options(self):
        if self.field_type == "dropdown":
            if not self.options or len(self.options) == 0:
                raise ValueError(
                    "options must be a non-empty list of strings when field_type is 'dropdown'"
                )
            # Ensure all options are non-empty strings
            for opt in self.options:
                if not isinstance(opt, str) or not opt.strip():
                    raise ValueError("Each dropdown option must be a non-empty string")
        return self


class CustomFieldUpdate(BaseModel):
    """Update a custom field definition (cannot change field_type)"""

    field_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Field name (alphanumeric + underscore only)",
    )
    options: Optional[List[str]] = Field(
        None,
        description="Dropdown choices (only for dropdown fields)",
    )
    required: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("field_name")
    @classmethod
    def validate_field_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not FIELD_NAME_PATTERN.match(v):
                raise ValueError(
                    "field_name must contain only alphanumeric characters and underscores"
                )
        return v


class CustomFieldResponse(BaseModel):
    """Custom field definition response"""

    id: UUID
    company_id: UUID
    entity_type: str
    field_name: str
    field_type: str
    options: Optional[List[str]] = None
    required: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomFieldListResponse(BaseModel):
    """Custom field definition list response"""

    fields: List[CustomFieldResponse]
    total: int
