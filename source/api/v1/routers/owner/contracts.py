"""
Owner contract management endpoints
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from db import get_session
from db.models.owner import Owner
from db.models.company import Company
from db.models.contract import Contract
from db.models.user import User
from db.models.enums import ContractStatusEnum, RoleEnum
from api.v1.schemas.contract import (
    ContractCreateRequest,
    ContractUpdateRequest,
    ContractRenewRequest,
    ContractResponse,
    ContractDetailResponse,
)

router = APIRouter(prefix="/contracts", tags=["Owner Contract Management"])


async def _build_detail_response(contract: Contract, session: AsyncSession) -> dict:
    """Build a detail response dict with current usage counts."""
    company = await session.get(Company, contract.company_id)
    company_name = company.name if company else None

    days_until_expiry = (contract.end_date - date.today()).days if contract.end_date else None

    admin_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == contract.company_id,
            User.role == RoleEnum.COMPANY_ADMIN,
            User.deleted_at.is_(None),
        )
    ) or 0

    manager_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == contract.company_id,
            User.role == RoleEnum.COMPANY_MANAGER,
            User.deleted_at.is_(None),
        )
    ) or 0

    operator_count = await session.scalar(
        select(func.count()).select_from(User).where(
            User.company_id == contract.company_id,
            User.role == RoleEnum.COMPANY_OPERATOR,
            User.deleted_at.is_(None),
        )
    ) or 0

    data = {
        k: v for k, v in contract.__dict__.items() if not k.startswith("_")
    }
    data["company_name"] = company_name
    data["days_until_expiry"] = days_until_expiry
    data["current_admins"] = admin_count
    data["current_managers"] = manager_count
    data["current_operators"] = operator_count
    return data


@router.post("", response_model=ContractDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreateRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a contract for a company.

    Validates company ownership and ensures no duplicate active contracts.
    """
    company = await Company.get(
        session=session, id=data.company_id, owner_id=owner.id
    )
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found or does not belong to you"
        )

    from utils.contract_enforcement import get_active_contract
    existing = await get_active_contract(data.company_id, session)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company already has an active contract"
        )

    create_fields = data.model_dump(exclude={"company_id", "metadata_"}, by_alias=False)
    contract = await Contract.create(
        session=session,
        owner_id=owner.id,
        company_id=data.company_id,
        metadata_=data.metadata_,
        **create_fields,
    )

    detail = await _build_detail_response(contract, session)
    return ContractDetailResponse(**detail)


@router.get("", response_model=List[ContractResponse])
async def list_contracts(
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
    company_id: Optional[UUID] = Query(None),
    contract_status: Optional[ContractStatusEnum] = Query(None, alias="status"),
):
    """List all contracts owned by the current owner, with optional filters."""
    filters = {"owner_id": owner.id}
    if company_id:
        filters["company_id"] = company_id
    if contract_status:
        filters["status"] = contract_status

    contracts = await Contract.get_all(
        session=session,
        order_by=(Contract.created_at.desc(),),
        **filters,
    )

    results = []
    for c in contracts:
        company = await session.get(Company, c.company_id)
        company_name = company.name if company else None
        days_until_expiry = (c.end_date - date.today()).days if c.end_date else None
        d = {k: v for k, v in c.__dict__.items() if not k.startswith("_")}
        d["company_name"] = company_name
        d["days_until_expiry"] = days_until_expiry
        results.append(ContractResponse(**d))

    return results


@router.get("/{contract_id}", response_model=ContractDetailResponse)
async def get_contract(
    contract_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """Get detailed contract information with current usage counts."""
    contract = await Contract.get_or_404(
        session=session, id=contract_id, owner_id=owner.id
    )
    detail = await _build_detail_response(contract, session)
    return ContractDetailResponse(**detail)


@router.put("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: UUID,
    data: ContractUpdateRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """Update contract limits, pricing, or payment status."""
    contract = await Contract.get_or_404(
        session=session, id=contract_id, owner_id=owner.id
    )

    update_data = data.model_dump(exclude_unset=True, by_alias=False)

    if "metadata_" in update_data:
        contract.metadata_ = update_data.pop("metadata_")

    for field, value in update_data.items():
        setattr(contract, field, value)

    await contract.update(session=session)

    company = await session.get(Company, contract.company_id)
    company_name = company.name if company else None
    days_until_expiry = (contract.end_date - date.today()).days if contract.end_date else None
    d = {k: v for k, v in contract.__dict__.items() if not k.startswith("_")}
    d["company_name"] = company_name
    d["days_until_expiry"] = days_until_expiry
    return ContractResponse(**d)


@router.post("/{contract_id}/renew", response_model=ContractResponse)
async def renew_contract(
    contract_id: UUID,
    data: ContractRenewRequest,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """Renew a contract: reset status to ACTIVE and extend end_date."""
    contract = await Contract.get_or_404(
        session=session, id=contract_id, owner_id=owner.id
    )

    contract.status = ContractStatusEnum.ACTIVE
    contract.payment_status = "paid"
    contract.end_date = data.new_end_date
    contract.is_active = True

    if data.next_payment_date is not None:
        contract.next_payment_date = data.next_payment_date
    if data.price is not None:
        contract.price = data.price

    await contract.update(session=session)

    company = await session.get(Company, contract.company_id)
    company_name = company.name if company else None
    days_until_expiry = (contract.end_date - date.today()).days if contract.end_date else None
    d = {k: v for k, v in contract.__dict__.items() if not k.startswith("_")}
    d["company_name"] = company_name
    d["days_until_expiry"] = days_until_expiry
    return ContractResponse(**d)


@router.post("/{contract_id}/cancel", response_model=ContractResponse)
async def cancel_contract(
    contract_id: UUID,
    owner: Owner = Owner.current(),
    session: AsyncSession = Depends(get_session),
):
    """Cancel a contract."""
    contract = await Contract.get_or_404(
        session=session, id=contract_id, owner_id=owner.id
    )

    contract.status = ContractStatusEnum.CANCELLED
    contract.is_active = False
    await contract.update(session=session)

    company = await session.get(Company, contract.company_id)
    company_name = company.name if company else None
    days_until_expiry = (contract.end_date - date.today()).days if contract.end_date else None
    d = {k: v for k, v in contract.__dict__.items() if not k.startswith("_")}
    d["company_name"] = company_name
    d["days_until_expiry"] = days_until_expiry
    return ContractResponse(**d)
