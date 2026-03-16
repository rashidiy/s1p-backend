"""
Owner's company management endpoints
"""

import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID, uuid4

from db import get_session
from db.models.owner import Owner
from db.models.company import Company
from db.models.user import User
from db.models.enums import ProviderEnum, RoleEnum
from api.v1.schemas.owner import (
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
    CompanyDetailResponse,
    InviteAdminRequest,
    InviteAdminResponse,
)
from api.v1.schemas.user import UserResponse
from utils.managers import PasswordManager, JWTManager, TokenType
from utils.contract_enforcement import check_user_limit
from utils.permissions import ROLE_PERMISSIONS
from core.config import AppConfig

router = APIRouter(prefix="/companies", tags=["Owner Company Management"])

IMPERSONATE_SHADOW_EMAIL_PREFIX = "owner-shadow-"


def _shadow_email(owner_id: UUID) -> str:
    return f"{IMPERSONATE_SHADOW_EMAIL_PREFIX}{owner_id}@s1p.internal"


async def _create_shadow_user(
    session: AsyncSession, owner: Owner, company_id: UUID
) -> User:
    """Create an invisible shadow admin user for the owner in a company."""
    return await User.create(
        session=session,
        email=_shadow_email(owner.id),
        first_name=owner.first_name or "Owner",
        last_name=owner.last_name,
        phone="",
        company_id=company_id,
        role=RoleEnum.COMPANY_ADMIN,
        permissions=ROLE_PERMISSIONS[RoleEnum.COMPANY_ADMIN],
        password_hash=PasswordManager.hash(secrets.token_urlsafe(32)),
        is_active=True,
        is_suspended=False,
        is_shadow=True,
        email_verified=True,
    )


@router.post("/{company_id}/impersonate")
async def impersonate_company(
    company_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a short-lived company-scoped token so the owner can access
    a company's CRM as an admin.

    Returns: { token: str, url: str }
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id,
    )
    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot impersonate an inactive company",
        )

    # Look up the shadow user (created when company was created)
    shadow_user = await User.get(
        email=_shadow_email(owner.id),
        company_id=company.id,
        session=session,
    )
    if not shadow_user:
        # Fallback: create if missing (e.g. companies created before this change)
        shadow_user = await _create_shadow_user(session, owner, company.id)

    # Issue a short-lived access token (15 min, no refresh)
    token = JWTManager.create(
        sub=shadow_user.id,
        token_type=TokenType.ACCESS,
        company_id=company.id,
        role=RoleEnum.COMPANY_ADMIN.value,
        permissions=ROLE_PERMISSIONS[RoleEnum.COMPANY_ADMIN],
        data={"impersonated_by": str(owner.id)},
        duration=timedelta(minutes=15),
    )

    # Build the target URL using the frontend URL
    from urllib.parse import urlparse
    base = AppConfig.FRONTEND_URL.rstrip("/")
    parsed = urlparse(base)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""

    if company.subdomain:
        url = f"{parsed.scheme}://{company.subdomain}.{host}{port}/login?impersonate={token}"
    else:
        url = f"{base}/login?impersonate={token}"

    return {"token": token, "url": url}


async def _get_users_count(session: AsyncSession, company_id: UUID) -> int:
    result = await session.execute(
        select(func.count(User.id)).where(
            User.company_id == company_id,
            User.deleted_at.is_(None),
            User.is_shadow.is_(False),
        )
    )
    return result.scalar_one()


@router.post("", response_model=CompanyDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreateRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
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
    else:
        # Check uniqueness for user-provided subdomain
        existing = await Company.get(session=session, subdomain=subdomain)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A company with this subdomain already exists",
            )

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

    # Create shadow admin user for owner impersonation
    await _create_shadow_user(session, owner, company.id)

    # Add computed fields
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{webhook_token}"
    company.users_count = 0

    return company


@router.post("/{company_id}/invite-admin", response_model=InviteAdminResponse, status_code=status.HTTP_201_CREATED)
async def invite_admin(
    company_id: UUID,
    data: InviteAdminRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Invite a company admin via Telegram invite token flow.

    Creates an InviteToken with COMPANY_ADMIN role.
    Returns the plaintext token and deep link — no user is created until registration.
    """
    company = await Company.get_or_404(
        session=session,
        id=company_id,
        owner_id=owner.id,
    )

    # Check contract user limit
    await check_user_limit(company.id, RoleEnum.COMPANY_ADMIN, session)

    # Check if phone already in use (if provided)
    if data.phone:
        existing_user = await User.get(
            session=session,
            phone=data.phone,
            company_id=company.id,
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this phone already exists in this company",
            )

    # Generate token
    from utils.services.invite_token_service import generate_invite_token, hash_invite_token
    from db.models.invite_token import InviteToken

    raw_token = generate_invite_token()
    token_hash = hash_invite_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=48)

    invite = await InviteToken.create(
        session=session,
        company_id=company.id,
        token_hash=token_hash,
        role=RoleEnum.COMPANY_ADMIN,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        permissions=ROLE_PERMISSIONS.get(RoleEnum.COMPANY_ADMIN, []),
        created_by=None,  # Owner doesn't have a User record in this company
        expires_at=expires_at,
    )

    return InviteAdminResponse(
        invite_token=raw_token,
        company_name=company.name,
        expires_at=expires_at,
        role=RoleEnum.COMPANY_ADMIN.value,
        first_name=data.first_name,
        phone=data.phone,
    )


@router.get("", response_model=List[CompanyResponse])
async def list_companies(
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
    search: Optional[str] = Query(None, description="Search by company name or subdomain"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """
    List all companies owned by the current owner

    Returns a list of all companies with basic information.
    Supports search by name/subdomain and pagination.
    """
    user_count_subq = (
        select(func.count(User.id))
        .where(User.company_id == Company.id, User.deleted_at.is_(None), User.is_shadow.is_(False))
        .correlate(Company)
        .scalar_subquery()
    )

    # Build base query
    query = select(Company, user_count_subq.label("users_count")).where(
        Company.owner_id == owner.id,
        Company.deleted_at.is_(None),
    )

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Company.name.ilike(search_term),
                Company.subdomain.ilike(search_term),
            )
        )

    query = query.order_by(Company.created_at.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result_rows = await session.execute(query)
    companies_with_counts = result_rows.all()

    # Add computed fields
    result = []
    for company, users_count in companies_with_counts:
        company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"
        company.users_count = users_count
        result.append(company)

    return result


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

    # Add computed fields
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"
    company.users_count = await _get_users_count(session, company.id)

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

    # Add computed fields
    company.webhook_url = f"{AppConfig.BASE_URL}/api/v1/company/webhooks/{company.webhook_token}"
    company.users_count = await _get_users_count(session, company.id)

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
    company.users_count = await _get_users_count(session, company.id)

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
    company.users_count = await _get_users_count(session, company.id)

    return company
