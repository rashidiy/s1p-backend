"""
Shared field validators for schemas
"""

import re
from typing import Dict, Any, List, Optional
from pydantic import field_validator


PASSWORD_PATTERN = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')
PASSWORD_ERROR = "Password must be at least 8 characters with at least one uppercase letter and one digit"

CUSTOM_FIELD_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')


class PasswordValidator:
    """Mixin for schemas that accept a password field."""

    @field_validator('password', 'new_password', check_fields=False)
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not PASSWORD_PATTERN.match(v):
            raise ValueError(PASSWORD_ERROR)
        return v


class CustomFieldsValidator:
    """Mixin for schemas that accept custom_fields."""

    @field_validator('custom_fields', check_fields=False)
    @classmethod
    def validate_custom_fields(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return v
        if len(v) > 50:
            raise ValueError('Maximum 50 custom fields allowed')
        for key, value in v.items():
            if len(key) > 100:
                raise ValueError(f'Custom field key "{key[:20]}..." exceeds 100 characters')
            if not CUSTOM_FIELD_KEY_PATTERN.match(key):
                raise ValueError(f'Custom field key "{key[:20]}" must be alphanumeric or underscore only')
            if isinstance(value, str) and len(value) > 10000:
                raise ValueError(f'Custom field "{key}" value exceeds 10,000 characters')
        return v


class TagsValidator:
    """Mixin for schemas that accept tags."""

    @field_validator('tags', check_fields=False)
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError('Maximum 20 tags allowed')
        cleaned = []
        seen = set()
        for tag in v:
            tag = tag.strip()
            if len(tag) > 50:
                raise ValueError(f'Tag "{tag[:20]}..." exceeds 50 characters')
            lower = tag.lower()
            if lower not in seen:
                seen.add(lower)
                cleaned.append(tag)
        return cleaned
