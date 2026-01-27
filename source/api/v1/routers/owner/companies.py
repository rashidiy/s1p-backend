"""
Owner's company management endpoints
"""

import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID, uuid4

from db import get_session
from db.models.owner import Owner
from db.models.company import Company
from db.models.enums import ProviderEnum
from api.v1.schemas.owner import (
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
    CompanyDetailResponse
)
from core.config import AppConfig

router = APIRouter(prefix="/companies", tags=["Owner Company Management"])


@router.post("/", response_model=CompanyDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreateRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new company

    Only owners can create companies. The owner selects the telephony provider
    (Sipuni or Binotel) and provides the provider configuration.

    The provider cannot be changed after company creation.
    """
    # Validate provider type
    try:
        provider_type = ProviderEnum(data.provider_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider type. Must be one of: {[e.value for e in ProviderEnum]}"
        )

    # Generate unique webhook token
    webhook_token = secrets.token_urlsafe(32)

    # Generate subdomain if not provided
    subdomain = data.subdomain
    if not subdomain:
        # Generate from company name
        subdomain = re.sub(r'[^a-z0-9]', '', data.name.lower())[:20]
        if not subdomain:
            subdomain = f"company_{uuid4().hex[:8]}"
        # Check uniqueness and append random suffix if needed
        existing = await Company.get(session=session, subdomain=subdomain)
        if existing:
            subdomain = f"{subdomain}_{uuid4().hex[:6]}"

    # Create company
    company = await Company.create(
        session=session,
        name=data.name,
        subdomain=subdomain,
        owner_id=owner.id,
        provider_type=provider_type,
        provider_config=data.provider_config,
        webhook_token=webhook_token,
        is_active=True
    )

    # Add webhook URL to response
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{webhook_token}"

    return company


@router.get("/", response_model=List[CompanyResponse])
async def list_companies(
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    List all companies owned by the current owner

    Returns a list of all companies with basic information.
    """
    companies = await Company.get_all(
        session=session,
        owner_id=owner.id,
        order_by=(Company.created_at.desc(),)
    )

    # Add webhook URLs
    for company in companies:
        company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"

    return companies


@router.get("/{company_id}", response_model=CompanyDetailResponse)
async def get_company(
    company_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get detailed information about a specific company

    Includes provider configuration and settings.
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id
    )

    # Add webhook URL
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"

    return company


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdateRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update company information

    Can update name, settings, and active status.
    Provider type and configuration cannot be changed.
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id
    )

    # Update fields
    if data.name is not None:
        company.name = data.name
    if data.settings is not None:
        company.settings = data.settings
    if data.is_active is not None:
        company.is_active = data.is_active

    await company.update(session=session)

    # Add webhook URL
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"

    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    hard: bool = False,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a company

    By default performs soft delete (can be restored).
    Use hard=true for permanent deletion.
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id
    )

    await company.delete(session=session, hard=hard)

    return None


@router.post("/{company_id}/activate", response_model=CompanyResponse)
async def activate_company(
    company_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Activate a suspended company
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id
    )

    company.is_active = True
    await company.update(session=session)

    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"

    return company


@router.post("/{company_id}/deactivate", response_model=CompanyResponse)
async def deactivate_company(
    company_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Deactivate a company (suspend access)
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id
    )

    company.is_active = False
    await company.update(session=session)

    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"

    return company
