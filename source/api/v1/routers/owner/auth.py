"""
Owner authentication endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.owner import Owner
from db.models.enums import RoleEnum
from api.v1.schemas.owner import OwnerRegisterRequest, OwnerWithCredentials, OwnerResponse
from utils.managers import PasswordManager, JWTManager

router = APIRouter(prefix="/auth", tags=["Owner Auth"])


@router.post('/register', response_model=OwnerWithCredentials)
async def register_owner(
    data: OwnerRegisterRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Register a new owner account

    Owners are platform administrators who can create and manage multiple companies.
    """
    # Check if owner already exists
    existing_owner = await Owner.get(email=data.email, session=session)
    if existing_owner:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Owner with this email already exists"
        )

    # Create owner
    owner = await Owner.create(
        session=session,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        password_hash=PasswordManager.hash(data.password),
        is_active=True,  # Auto-activate owners (or require email verification)
        email_verified=False
    )

    # Generate JWT credentials
    owner.credentials = JWTManager.generate_credentials(
        sub=owner.id,
        company_id=None,  # Owners don't belong to a company
        role=RoleEnum.OWNER.value,
        permissions=["*"]  # Owners have all permissions
    )

    return owner


@router.post('/login', response_model=OwnerWithCredentials)
async def login_owner(
    email: str,
    password: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Owner login

    Returns JWT tokens for authenticated owner.
    """
    owner = await Owner.get(email=email, session=session)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not PasswordManager.verify(password, owner.password_hash):
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
async def get_current_owner(owner: Owner = Depends(Owner.current)):
    """
    Get current owner profile

    Requires authentication via JWT token.
    """
    return owner
