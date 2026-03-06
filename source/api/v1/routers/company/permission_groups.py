"""
Permission group management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from uuid import UUID

from db import get_session
from db.models.user import User
from db.models.permission_group import PermissionGroup
from api.v1.schemas.permission_group import (
    PermissionGroupCreateRequest,
    PermissionGroupUpdateRequest,
    PermissionGroupResponse,
    PermissionGroupListResponse,
)
from utils.permissions import require_permissions, Permissions

router = APIRouter(prefix="/permission-groups", tags=["Permission Groups"])


@router.get("/permissions", tags=["Permission Groups"])
async def list_available_permissions(user: User = User.current()):
    """
    List all available permission strings

    Returns permissions grouped by resource.
    """
    all_perms = sorted(Permissions.all())
    grouped = {}
    for perm in all_perms:
        resource = perm.split(".")[0]
        grouped.setdefault(resource, []).append(perm)
    return {"permissions": all_perms, "grouped": grouped}


@router.get("", response_model=PermissionGroupListResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def list_permission_groups(
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    List all permission groups available to the company

    Returns system groups (shared) + company-specific custom groups.
    """
    query = select(PermissionGroup).where(
        PermissionGroup.deleted_at.is_(None),
        or_(
            PermissionGroup.company_id.is_(None),
            PermissionGroup.company_id == user.company_id,
        ),
    )
    query = query.order_by(PermissionGroup.is_system.desc(), PermissionGroup.name)

    result = await session.execute(query)
    groups = result.scalars().all()

    return PermissionGroupListResponse(groups=groups, total=len(groups))


@router.get("/{group_id}", response_model=PermissionGroupResponse)
@require_permissions(Permissions.SETTINGS_READ)
async def get_permission_group(
    group_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Get a single permission group

    Returns the group only if it's a system group or belongs to the user's company.
    Returns 404 for groups belonging to other companies (no existence leak).
    """
    query = select(PermissionGroup).where(
        PermissionGroup.id == group_id,
        PermissionGroup.deleted_at.is_(None),
        or_(
            PermissionGroup.company_id.is_(None),
            PermissionGroup.company_id == user.company_id,
        ),
    )
    result = await session.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission group not found")

    return group


@router.post("", response_model=PermissionGroupResponse, status_code=status.HTTP_201_CREATED)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def create_permission_group(
    data: PermissionGroupCreateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a custom permission group for the company
    """
    # Check name uniqueness within company
    existing = await PermissionGroup.get(
        name=data.name,
        company_id=user.company_id,
        session=session,
    )
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A permission group with this name already exists in your company",
        )

    group = await PermissionGroup.create(
        session=session,
        name=data.name,
        description=data.description,
        permissions=data.permissions,
        company_id=user.company_id,
        is_system=False,
    )

    return group


@router.put("/{group_id}", response_model=PermissionGroupResponse)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def update_permission_group(
    group_id: UUID,
    data: PermissionGroupUpdateRequest,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Update a custom permission group

    Only company-owned groups can be modified. System groups cannot be modified.
    """
    query = select(PermissionGroup).where(
        PermissionGroup.id == group_id,
        PermissionGroup.deleted_at.is_(None),
    )
    result = await session.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission group not found")

    # System groups cannot be modified
    if group.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System groups cannot be modified")

    # Only allow updating groups owned by the user's company
    if group.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission group not found")

    if data.name is not None:
        # Check name uniqueness
        existing = await PermissionGroup.get(
            name=data.name,
            company_id=user.company_id,
            session=session,
        )
        if existing and existing.id != group.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A permission group with this name already exists in your company",
            )
        group.name = data.name

    if data.description is not None:
        group.description = data.description
    if data.permissions is not None:
        group.permissions = data.permissions

    await group.update(session=session)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permissions(Permissions.SETTINGS_MANAGE)
async def delete_permission_group(
    group_id: UUID,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Soft-delete a custom permission group

    System groups cannot be deleted.
    Nullifies permission_group_id on affected users before deleting.
    """
    query = select(PermissionGroup).where(
        PermissionGroup.id == group_id,
        PermissionGroup.deleted_at.is_(None),
    )
    result = await session.execute(query)
    group = result.scalar_one_or_none()

    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission group not found")

    # System groups cannot be deleted
    if group.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System groups cannot be deleted")

    # Only allow deleting groups owned by the user's company
    if group.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission group not found")

    # Nullify permission_group_id on affected users
    await User.update_by(
        session=session,
        values={"permission_group_id": None},
        commit=False,
        permission_group_id=group_id,
    )

    await group.delete(session=session)
    return None
