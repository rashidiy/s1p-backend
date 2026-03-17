"""
Common base schemas
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(BaseModel):
    """Mixin for models with timestamps"""
    created_at: datetime
    updated_at: Optional[datetime] = None


class UUIDMixin(BaseModel):
    """Mixin for models with UUID"""
    id: UUID


class PaginationParams(BaseModel):
    """Pagination parameters"""
    skip: int = 0
    limit: int = 100


class PaginatedResponse(BaseModel):
    """Paginated response wrapper"""
    total: int
    skip: int
    limit: int
    items: list


class MessageResponse(BaseModel):
    """Simple message response"""
    message: str
    success: bool = True
