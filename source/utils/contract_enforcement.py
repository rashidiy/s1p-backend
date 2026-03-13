"""
Contract enforcement utilities
"""

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.contract import Contract
from db.models.user import User
from db.models.enums import ContractStatusEnum, RoleEnum


_ACCESS_STATUSES = (
    ContractStatusEnum.ACTIVE,
    ContractStatusEnum.WARNING,
    ContractStatusEnum.GRACE_PERIOD,
)


async def get_active_contract(company_id, session: AsyncSession) -> Contract | None:
    """Get the active contract for a company (status in ACTIVE, WARNING, GRACE_PERIOD)."""
    result = await session.execute(
        select(Contract).where(
            Contract.company_id == company_id,
            Contract.status.in_(_ACCESS_STATUSES),
            Contract.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def check_contract_active(company_id, session: AsyncSession) -> None:
    """
    Raise 403 if the company has a contract but none with active access.

    If no contract exists at all, skip (backward compatibility).
    """
    has_any = await session.scalar(
        select(func.count()).select_from(Contract).where(
            Contract.company_id == company_id,
            Contract.deleted_at.is_(None),
        )
    )
    if not has_any:
        return

    contract = await get_active_contract(company_id, session)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company contract has expired or been suspended. Contact your administrator."
        )


_ROLE_LIMIT_MAP = {
    RoleEnum.COMPANY_ADMIN: "max_admins",
    RoleEnum.COMPANY_MANAGER: "max_managers",
    RoleEnum.COMPANY_OPERATOR: "max_operators",
}


async def check_user_limit(company_id, role: RoleEnum, session: AsyncSession) -> None:
    """Raise 403 if adding another user of this role would exceed the contract limit."""
    limit_field = _ROLE_LIMIT_MAP.get(role)
    if not limit_field:
        return

    contract = await get_active_contract(company_id, session)
    if not contract:
        return

    current_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == company_id,
            User.role == role,
            User.deleted_at.is_(None),
            User.is_shadow.is_(False),
        )
    )

    limit = getattr(contract, limit_field)
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Contract limit reached: maximum {limit} {role.value}s allowed"
        )
