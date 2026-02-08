"""
Owner authentication endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.owner import Owner
from db.models.enums import RoleEnum
from api.v1.schemas.owner import OwnerWithCredentials, OwnerResponse
from utils.managers import PasswordManager, JWTManager

router = APIRouter(prefix="/auth", tags=["Owner Auth"])


class OwnerLoginRequest(BaseModel):
    """Owner login request schema"""
    email: str
    password: str


@router.post('/login', response_model=OwnerWithCredentials)
async def login_owner(
    data: OwnerLoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Owner login

    Returns JWT tokens for authenticated owner.
    """
    owner = await Owner.get(email=data.email, session=session)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not PasswordManager.verify(data.password, owner.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid email or password"
        )

    if not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner account is inactive"
        )

    # Generate JWT credentials
    owner.credentials = JWTManager.generate_credentials(
        sub=owner.id,
        company_id=None,
        role=RoleEnum.OWNER.value,
        permissions=["*"]
    )

    return owner


@router.get('/me', response_model=OwnerResponse)
async def get_current_owner(owner: Owner = Owner.current()):
    """
    Get current owner profile

    Requires authentication via JWT token.
    """
    return owner
