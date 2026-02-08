"""
Shared field validators for schemas
"""

import re
from pydantic import field_validator


PASSWORD_PATTERN = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')
PASSWORD_ERROR = "Password must be at least 8 characters with at least one uppercase letter and one digit"


class PasswordValidator:
    """Mixin for schemas that accept a password field."""

    @field_validator('password', 'new_password', check_fields=False)
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not PASSWORD_PATTERN.match(v):
            raise ValueError(PASSWORD_ERROR)
        return v
