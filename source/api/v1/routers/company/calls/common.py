"""
Provider-agnostic call endpoints and shared helpers
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID as PyUUID

from db import get_session
from db.models.user import User
from db.models.company import Company
from db.models.call_event import CallEvent
from db.models.enums import ProviderEnum, RoleEnum
from api.v1.schemas.call import CallEventResponse
from utils.permissions import require_permissions, Permissions


# ---------------------------------------------------------------------------
# Shared helpers (used by sipuni.py / binotel.py)
# ---------------------------------------------------------------------------

async def resolve_operator_id(
    operator_id: Optional[str],
    company_id: PyUUID,
    session: AsyncSession,
) -> Optional[PyUUID]:
    """Resolve operator_id string to a user UUID.

    Accepts UUID, phone, or email. Returns None if not found.
    """
    if not operator_id:
        return None

    # Try UUID first
    try:
        uid = PyUUID(operator_id)
        user = await User.get(id=uid, company_id=company_id, session=session)
        if user:
            return user.id
    except ValueError:
        pass

    # Try phone
    user = await User.get(phone=operator_id, company_id=company_id, session=session)
    if user:
        return user.id

    # Try email
    user = await User.get(email=operator_id, company_id=company_id, session=session)
    if user:
        return user.id

    return None


async def get_active_company(user: User, session: AsyncSession) -> Company:
    """Get the user's company and verify it's active."""
    company = await Company.get_or_404(id=user.company_id, session=session)
    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company is not active"
        )
    return company


async def next_call_number(session: AsyncSession, company_id: PyUUID) -> int:
    """Return the next company-scoped call number (max + 1).

    Uses SELECT FOR UPDATE to prevent concurrent reads from getting the same MAX.
    """
    result = await session.execute(
        select(func.coalesce(func.max(CallEvent.id), 0) + 1)
        .where(CallEvent.company_id == company_id)
        .with_for_update()
    )
    return result.scalar_one()


def require_provider(expected: ProviderEnum):
    """Return a dependency that validates the company uses the expected provider."""

    async def _check(
        user: User = User.current(),
        session: AsyncSession = Depends(get_session),
    ) -> Company:
        company = await get_active_company(user, session)
        if company.provider_type != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This endpoint is only available for {expected.value} companies"
            )
        return company

    return _check


# ---------------------------------------------------------------------------
# Provider-agnostic read endpoints
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/calls", tags=["Calls"])


@router.get("", response_model=List[CallEventResponse])
@require_permissions(Permissions.CALLS_READ)
async def list_calls(
    skip: int = 0,
    limit: int = 100,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    List all calls

    Returns call events ordered by most recent first.
    Operators only see their own calls. Admins and Managers see all company calls.
    """
    filters = {"company_id": user.company_id}
    if user.role == RoleEnum.COMPANY_OPERATOR:
        filters["operator_id"] = user.id

    calls = await CallEvent.get_all(
        session=session,
        offset=skip,
        limit=limit,
        order_by=(CallEvent.created_at.desc(),),
        **filters
    )
    return calls


@router.get("/{call_id}", response_model=CallEventResponse)
@require_permissions(Permissions.CALLS_READ)
async def get_call(
    call_id: int,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Get call details

    Returns a single call event by its company-scoped ID.
    Requires CALLS_READ permission.
    """
    call = await CallEvent.get_or_404(
        session=session,
        id=call_id,
        company_id=user.company_id
    )
    return call


