"""
User management endpoints (Company Admin manages operators)
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select
from typing import List, Optional
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from db.models.lead import Lead
from db.models.deal import Deal
from db.models.task import Task
from db.models.permission_group import PermissionGroup
from db.models.invite_token import InviteToken
from db.models.enums import RoleEnum
from api.v1.schemas.user import (
    UserInviteRequest,
    UserUpdateRequest,
    UserResponse,
    UserDetailResponse,
    UserListResponse,
    ProfileUpdateRequest,
)
from api.v1.schemas.telegram_auth import (
    InviteTokenCreateRequest,
    InviteTokenCreateResponse,
    InviteTokenListItem,
    InviteTokenListResponse,
)
from utils.managers import PasswordManager
from utils.permissions import require_permissions, Permissions, ROLE_PERMISSIONS
from utils.contract_enforcement import check_user_limit
from utils.services.email_service import EmailService
from utils.services.invite_token_service import generate_invite_token, hash_invite_token
from core.config import AppConfig

router = APIRouter(prefix="/users", tags=["User Management"])


@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.USERS_CREATE)
async def invite_operator(
    data: UserInviteRequest,
    background_tasks: BackgroundTasks,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Invite a new operator (Company Admin only)

    Sends email invitation with temporary password.
    Operator must change password on first login.
    """
    # Check if user already exists in this company
    existing_user = await User.get(
        email=data.email,
        company_id=admin.company_id,
        session=session
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists in your company"
        )

    # Validate role
    try:
        role = RoleEnum(data.role)
        if role == RoleEnum.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create owner-level users"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[e.value for e in RoleEnum if e != RoleEnum.OWNER]}"
        )

    # Check contract user limit
    await check_user_limit(admin.company_id, role, session)

    # Validate permission_group_id if provided
    permission_group_id = None
    if data.permission_group_id:
        group = await PermissionGroup.get(id=data.permission_group_id, session=session)
        if not group:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Permission group not found")
        if group.company_id is not None and group.company_id != admin.company_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Permission group does not belong to this company")
        permission_group_id = group.id

    # Generate temporary password
    temporary_password = EmailService.generate_temporary_password()

    # Create user
    user = await User.create(
        session=session,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone or "",
        company_id=admin.company_id,
        role=role,
        permissions=data.permissions if data.permissions else ROLE_PERMISSIONS.get(role, []),
        permission_group_id=permission_group_id,
        password_hash=PasswordManager.hash(temporary_password),
        is_active=True,
        is_suspended=False,
        email_verified=False
    )

    # Send invitation email
    from db.models.company import Company
    company = await session.get(Company, admin.company_id)
    company_name = company.name if company else "Your Company"

    role_display = role.value.replace("company_", "a ").title()
    EmailService.send_operator_invitation(
        background_tasks=background_tasks,
        to_email=user.email,
        company_name=company_name,
        temporary_password=temporary_password,
        invited_by=admin.full_name,
        role_display=role_display,
        login_url=f"{AppConfig.BASE_URL}/login",
    )

    return user


@router.get("/me", response_model=UserResponse)
async def get_my_profile(user: User = User.current()):
    """
    Get current user's own profile
    """
    return user


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    data: ProfileUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Update current user's own profile

    Only personal fields can be updated (name, phone, language).
    """
    if data.first_name is not None:
        user.first_name = data.first_name
    if data.last_name is not None:
        user.last_name = data.last_name
    if data.phone is not None:
        user.phone = data.phone
    if data.language is not None:
        user.language = data.language

    await user.update(session=session)
    return user


@router.get("", response_model=UserListResponse)
@require_permissions(Permissions.USERS_READ)
async def list_users(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
):
    """
    List all users in the company (Company Admin only)

    Supports pagination, filtering by role/status, and search.
    """
    filters = {"company_id": admin.company_id}

    if role:
        filters["role"] = RoleEnum(role)
    if is_active is not None:
        filters["is_active"] = is_active

    # Build query
    query = select(User).where(
        User.company_id == admin.company_id,
        User.deleted_at.is_(None)
    )

    # Search by name or email
    if search:
        from sqlalchemy import or_
        search_term = f"%{search}%"
        query = query.where(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(User.created_at.desc())

    result = await session.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        users=users,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{user_id}", response_model=UserDetailResponse)
@require_permissions(Permissions.USERS_READ)
async def get_user(
    user_id: UUID,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Get user details with statistics

    Includes total calls, leads, deals, and tasks.
    """
    user = await User.get_or_404(
        session=session,
        id=user_id,
        company_id=admin.company_id
    )

    # Get user statistics
    calls_count = await session.scalar(
        select(func.count()).select_from(CallEvent).where(
            CallEvent.operator_id == user_id
        )
    ) or 0

    leads_count = await session.scalar(
        select(func.count()).select_from(Lead).where(
            Lead.assigned_to == user_id
        )
    ) or 0

    deals_count = await session.scalar(
        select(func.count()).select_from(Deal).where(
            Deal.assigned_to == user_id
        )
    ) or 0

    tasks_count = await session.scalar(
        select(func.count()).select_from(Task).where(
            Task.assigned_to == user_id
        )
    ) or 0

    # Create response with stats
    user_dict = {
        **{k: v for k, v in user.__dict__.items() if not k.startswith('_')},
        "total_calls": calls_count,
        "total_leads": leads_count,
        "total_deals": deals_count,
        "total_tasks": tasks_count
    }

    return UserDetailResponse(**user_dict)


@router.put("/{user_id}", response_model=UserResponse)
@require_permissions(Permissions.USERS_UPDATE)
async def update_user(
    user_id: UUID,
    data: UserUpdateRequest,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Update user information (Company Admin only)

    Can update name, phone, role, permissions, and status.
    """
    user = await User.get_or_404(
        session=session,
        id=user_id,
        company_id=admin.company_id
    )

    # Update fields
    if data.first_name is not None:
        user.first_name = data.first_name
    if data.last_name is not None:
        user.last_name = data.last_name
    if data.phone is not None:
        user.phone = data.phone
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_suspended is not None:
        user.is_suspended = data.is_suspended
    if data.role is not None:
        role = RoleEnum(data.role)
        if role == RoleEnum.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change user to owner role"
            )
        user.role = role
    if data.permissions is not None:
        user.permissions = data.permissions
    if data.permission_group_id is not None:
        group = await PermissionGroup.get(id=data.permission_group_id, session=session)
        if not group:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Permission group not found")
        if group.company_id is not None and group.company_id != admin.company_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Permission group does not belong to this company")
        user.permission_group_id = group.id

    await user.update(session=session)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.USERS_DELETE)
async def delete_user(
    user_id: UUID,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
    hard: bool = False
):
    """
    Delete user (Company Admin only)

    By default performs soft delete (can be restored).
    Use hard=true for permanent deletion.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    user = await User.get_or_404(
        session=session,
        id=user_id,
        company_id=admin.company_id
    )

    await user.delete(session=session, hard=hard)
    return None


@router.post("/{user_id}/activate", response_model=UserResponse)
@require_permissions(Permissions.USERS_UPDATE)
async def activate_user(
    user_id: UUID,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Activate a suspended user
    """
    user = await User.get_or_404(
        session=session,
        id=user_id,
        company_id=admin.company_id
    )

    user.is_active = True
    user.is_suspended = False
    await user.update(session=session)

    return user


@router.post("/{user_id}/deactivate", response_model=UserResponse)
@require_permissions(Permissions.USERS_UPDATE)
async def deactivate_user(
    user_id: UUID,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session)
):
    """
    Deactivate a user (suspend access)
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself"
        )

    user = await User.get_or_404(
        session=session,
        id=user_id,
        company_id=admin.company_id
    )

    user.is_active = False
    user.is_suspended = True
    await user.update(session=session)

    return user


# ── Telegram Invite Token Endpoints ──────────────────────────────────


@router.post(
    "/invite-telegram",
    response_model=InviteTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permissions(Permissions.USERS_CREATE)
async def invite_telegram(
    data: InviteTokenCreateRequest,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Create an invite token for Telegram-based registration.

    Generates an XXXX-XXXX token shown once. Backend stores only SHA-256 hash.
    The invited user redeems this token via the Telegram bot /register flow.
    """
    # Validate role
    try:
        role = RoleEnum(data.role)
        if role == RoleEnum.OWNER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create owner-level users",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[e.value for e in RoleEnum if e != RoleEnum.OWNER]}",
        )

    # Validate permissions
    if data.permissions:
        valid = Permissions.all()
        invalid = [p for p in data.permissions if p not in valid]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid permissions: {invalid}",
            )

    # Validate permission group
    permission_group_id = None
    if data.permission_group_id:
        group = await PermissionGroup.get(id=data.permission_group_id, session=session)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Permission group not found",
            )
        if group.company_id is not None and group.company_id != admin.company_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Permission group not found",
            )
        permission_group_id = group.id

    # Check if phone already in use by an active user in this company
    existing_user = await User.get(
        session=session,
        phone=data.phone,
        company_id=admin.company_id,
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this phone already exists in your company",
        )

    # Check for active (unused + not expired) invite token for same phone+company
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(InviteToken).where(
            InviteToken.company_id == admin.company_id,
            InviteToken.phone == data.phone,
            InviteToken.used_at.is_(None),
            InviteToken.expires_at > now,
        )
    )
    active_invite = result.scalar_one_or_none()
    if active_invite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active invite already exists for this phone number",
        )

    # Generate token
    raw_token = generate_invite_token()
    token_hash = hash_invite_token(raw_token)
    expires_at = now + timedelta(hours=48)

    invite = await InviteToken.create(
        session=session,
        company_id=admin.company_id,
        token_hash=token_hash,
        role=role,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        permissions=data.permissions if data.permissions else ROLE_PERMISSIONS.get(role, []),
        permission_group_id=permission_group_id,
        created_by=admin.id,
        expires_at=expires_at,
    )

    return InviteTokenCreateResponse(
        invite_token=raw_token,
        expires_at=expires_at,
        role=role.value,
        first_name=data.first_name,
        phone=data.phone,
    )


@router.get("/invite-tokens", response_model=InviteTokenListResponse)
@require_permissions(Permissions.USERS_READ)
async def list_invite_tokens(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    token_status: Optional[str] = Query(None, alias="status"),
):
    """
    List invite tokens for the company.

    Supports filtering by status: pending, used, expired.
    """
    now = datetime.now(timezone.utc)

    query = select(InviteToken).where(
        InviteToken.company_id == admin.company_id,
    )

    if token_status == "pending":
        query = query.where(
            InviteToken.used_at.is_(None),
            InviteToken.expires_at > now,
        )
    elif token_status == "used":
        query = query.where(InviteToken.used_at.isnot(None))
    elif token_status == "expired":
        query = query.where(
            InviteToken.used_at.is_(None),
            InviteToken.expires_at <= now,
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    query = query.order_by(InviteToken.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    tokens = result.scalars().all()

    # Build response items with computed status and creator name
    items = []
    for token in tokens:
        # Compute status
        if token.used_at is not None:
            computed_status = "used"
        elif token.expires_at.replace(tzinfo=timezone.utc) < now:
            computed_status = "expired"
        else:
            computed_status = "pending"

        # Get creator name
        created_by_name = None
        if token.created_by:
            creator = await User.get(session=session, id=token.created_by, include_deleted=True)
            if creator:
                created_by_name = creator.full_name

        items.append(InviteTokenListItem(
            id=token.id,
            role=token.role.value if hasattr(token.role, 'value') else token.role,
            first_name=token.first_name,
            last_name=token.last_name,
            phone=token.phone,
            created_by_name=created_by_name,
            expires_at=token.expires_at,
            used_at=token.used_at,
            created_at=token.created_at,
            status=computed_status,
        ))

    return InviteTokenListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/invite-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.USERS_CREATE)
async def revoke_invite_token(
    token_id: UUID,
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Revoke (delete) an invite token.

    Hard-deletes the row. Cannot revoke already-used tokens.
    """
    invite = await InviteToken.get(
        session=session,
        id=token_id,
        company_id=admin.company_id,
    )
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite token not found",
        )

    if invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke a used invite token",
        )

    await session.delete(invite)
    await session.commit()
    return None
