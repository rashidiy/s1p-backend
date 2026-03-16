"""
Outbound webhook management endpoints

CRUD for webhook endpoints + delivery log.
"""

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.webhook import WebhookEndpoint, WebhookDelivery
from api.v1.schemas.webhook import (
    WebhookEndpointCreate,
    WebhookEndpointUpdate,
    WebhookEndpointResponse,
    WebhookDeliveryResponse,
    VALID_EVENTS,
)
from api.v1.schemas.crm import PaginatedResponse
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/outbound-webhooks", tags=["Outbound Webhooks"])


@router.post("", response_model=WebhookEndpointResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_webhook_endpoint(
    data: WebhookEndpointCreate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Create a new outbound webhook endpoint."""
    endpoint = await WebhookEndpoint.create(
        session=session,
        company_id=user.company_id,
        url=data.url,
        events=data.events,
        secret=data.secret,
    )
    return endpoint


@router.get("", response_model=PaginatedResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def list_webhook_endpoints(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List all outbound webhook endpoints for the company."""
    conditions = [WebhookEndpoint.company_id == user.company_id]
    if is_active is not None:
        conditions.append(WebhookEndpoint.is_active == is_active)

    count_query = select(func.count()).select_from(WebhookEndpoint).where(and_(*conditions))
    total = await session.scalar(count_query) or 0

    query = (
        select(WebhookEndpoint)
        .where(and_(*conditions))
        .order_by(WebhookEndpoint.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    endpoints = result.scalars().all()

    return PaginatedResponse(
        items=[WebhookEndpointResponse.model_validate(ep) for ep in endpoints],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.get("/events")
@require_permissions(Permissions.SETTINGS_READ)
async def list_available_events(user: User = User.current()):
    """List all available webhook event types."""
    return {"events": VALID_EVENTS}


@router.get("/{endpoint_id}", response_model=WebhookEndpointResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_webhook_endpoint(
    endpoint_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Get webhook endpoint details."""
    endpoint = await WebhookEndpoint.get_or_404(
        session=session,
        id=endpoint_id,
        company_id=user.company_id,
    )
    return endpoint


@router.put("/{endpoint_id}", response_model=WebhookEndpointResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_webhook_endpoint(
    endpoint_id: UUID,
    data: WebhookEndpointUpdate,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Update webhook endpoint configuration."""
    endpoint = await WebhookEndpoint.get_or_404(
        session=session,
        id=endpoint_id,
        company_id=user.company_id,
    )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(endpoint, field, value)

    await endpoint.update(session=session)
    return endpoint


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_webhook_endpoint(
    endpoint_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """Delete a webhook endpoint and all its delivery history."""
    endpoint = await WebhookEndpoint.get_or_404(
        session=session,
        id=endpoint_id,
        company_id=user.company_id,
    )
    await endpoint.delete(session=session, hard=True)
    return None


@router.get("/{endpoint_id}/deliveries", response_model=PaginatedResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def list_deliveries(
    endpoint_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List delivery log for a webhook endpoint."""
    # Verify endpoint belongs to this company
    endpoint = await WebhookEndpoint.get_or_404(
        session=session,
        id=endpoint_id,
        company_id=user.company_id,
    )

    conditions = [WebhookDelivery.endpoint_id == endpoint.id]
    if status_filter:
        conditions.append(WebhookDelivery.status == status_filter)

    count_query = select(func.count()).select_from(WebhookDelivery).where(and_(*conditions))
    total = await session.scalar(count_query) or 0

    query = (
        select(WebhookDelivery)
        .where(and_(*conditions))
        .order_by(WebhookDelivery.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(query)
    deliveries = result.scalars().all()

    return PaginatedResponse(
        items=[WebhookDeliveryResponse.model_validate(d) for d in deliveries],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )
