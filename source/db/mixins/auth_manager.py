from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from db import get_session
from utils.managers import JWTManager, TokenType

http_bearer = HTTPBearer()


class AuthenticationManagerMixin:
    @classmethod
    def current(
            cls, check_for_active: bool = True, check_for_suspended: bool = True
    ):
        async def authenticate(
                session: AsyncSession = Depends(get_session),
                credentials: HTTPAuthorizationCredentials = Depends(http_bearer)
        ):
            token = credentials.credentials
            payload = JWTManager.verify(token, TokenType.ACCESS)

            user = await cls.get(id=payload.sub, session=session)

            if check_for_active:
                if not user.is_active: raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive.")
            if check_for_suspended:
                if user.is_suspended: raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is suspended.")
            return user

        return Depends(authenticate)
