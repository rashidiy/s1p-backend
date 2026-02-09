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

            if not user:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found.")

            # Check for soft delete (if model has deleted_at attribute)
            if hasattr(user, 'deleted_at') and user.deleted_at is not None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Account has been deleted.")

            # Multi-tenant validation: ensure JWT company_id matches user's company_id
            if hasattr(user, 'company_id') and user.company_id:
                jwt_company_id = str(user.company_id) if user.company_id else None
                payload_company_id = str(payload.company_id) if payload.company_id else None

                if jwt_company_id != payload_company_id:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        "Token company mismatch. Please re-authenticate."
                    )

            if check_for_active:
                if not user.is_active:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is inactive.")
            if check_for_suspended:
                if user.is_suspended:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is suspended.")

            # Check contract status for company users
            if hasattr(user, 'company_id') and user.company_id:
                from utils.contract_enforcement import check_contract_active
                await check_contract_active(user.company_id, session)

            return user

        return Depends(authenticate)
