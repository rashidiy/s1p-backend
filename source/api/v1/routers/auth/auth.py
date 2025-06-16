from datetime import timedelta

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import AuthSchema
from db import get_session
from db.models import User
from utils.managers import PasswordManager, JWTManager, TokenType
from . import router


@router.post('/register', response_model=AuthSchema.AuthorizedResponse)
async def register(data: AuthSchema.RegisterRequest, session: AsyncSession = Depends(get_session)):
    user, created = await User.get_or_create(
        session=session,
        first_name=data.first_name,
        last_name=data.last_name,
        defaults={"email": data.email},
        password_hash=PasswordManager.hash(data.password),
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user.credentials = JWTManager.generate_credentials(user.id)
    return user


@router.post('/login', response_model=AuthSchema.AuthorizedResponse)
async def login(data: AuthSchema.LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await User.get(email=data.email, session=session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    if not PasswordManager.verify(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email or password incorrect.")

    user.credentials = JWTManager.generate_credentials(user.id, access_duration=timedelta(days=15))
    return user


@router.get('/refresh')
async def refresh_token(token: str = Query()):
    payload = JWTManager.verify(token, TokenType.REFRESH)
    return {"access": JWTManager.create(payload.sub, TokenType.ACCESS, payload.data)}
