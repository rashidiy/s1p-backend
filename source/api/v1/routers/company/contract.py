"""
Company contract status endpoint (read-only)
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.contract import Contract
from db.models.enums import ContractStatusEnum, PaymentStatusEnum, RoleEnum
from api.v1.schemas.contract import ContractStatusResponse
from utils.permissions import require_permissions, Permissions
from utils.contract_enforcement import get_active_contract

router = APIRouter(prefix="/contract", tags=["Company Contract"])


@router.get("", response_model=ContractStatusResponse)
@require_permissions(Permissions.CONTRACT_READ)
async def get_contract_status(
    admin: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Get company contract status

    Returns contract details including seat limits, current usage, expiry date,
    and any active warnings (expiring soon, payment issues, seat limits reached).
    Requires CONTRACT_READ permission.
    """
    contract = await get_active_contract(admin.company_id, session)

    if not contract:
        # Check if any contract exists at all
        any_contract = await session.scalar(
            select(func.count()).select_from(Contract).where(
                Contract.company_id == admin.company_id,
                Contract.deleted_at.is_(None),
            )
        )
        if any_contract:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active contract. Contact your administrator."
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contract found for this company"
        )

    # Count current users by role
    admin_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == admin.company_id,
            User.role == RoleEnum.COMPANY_ADMIN,
            User.deleted_at.is_(None),
        )
    ) or 0

    manager_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == admin.company_id,
            User.role == RoleEnum.COMPANY_MANAGER,
            User.deleted_at.is_(None),
        )
    ) or 0

    operator_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == admin.company_id,
            User.role == RoleEnum.COMPANY_OPERATOR,
            User.deleted_at.is_(None),
        )
    ) or 0

    days_until_expiry = (contract.end_date - date.today()).days if contract.end_date else None

    # Build warnings
    warnings = []
    if days_until_expiry is not None and days_until_expiry <= 30:
        warnings.append(f"Contract expires in {days_until_expiry} days")
    if contract.status == ContractStatusEnum.GRACE_PERIOD:
        warnings.append("Contract has expired. You are in the grace period.")
    if contract.payment_status in (PaymentStatusEnum.OVERDUE, PaymentStatusEnum.FAILED):
        warnings.append(f"Payment status: {contract.payment_status.value}")
    if admin_count >= contract.max_admins:
        warnings.append(f"Admin limit reached ({admin_count}/{contract.max_admins})")
    if manager_count >= contract.max_managers:
        warnings.append(f"Manager limit reached ({manager_count}/{contract.max_managers})")
    if operator_count >= contract.max_operators:
        warnings.append(f"Operator limit reached ({operator_count}/{contract.max_operators})")

    return ContractStatusResponse(
        id=contract.id,
        name=contract.name,
        status=contract.status,
        payment_status=contract.payment_status,
        max_admins=contract.max_admins,
        max_managers=contract.max_managers,
        max_operators=contract.max_operators,
        max_storage_gb=contract.max_storage_gb,
        current_admins=admin_count,
        current_managers=manager_count,
        current_operators=operator_count,
        start_date=contract.start_date,
        end_date=contract.end_date,
        days_until_expiry=days_until_expiry,
        billing_period=contract.billing_period,
        auto_renew=contract.auto_renew,
        warnings=warnings,
    )
