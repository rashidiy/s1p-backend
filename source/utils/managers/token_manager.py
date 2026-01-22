from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List
from uuid import UUID

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel
from starlette import status

from core import config


class JWTPayload(BaseModel):
    """JWT Payload with multi-tenant support"""
    sub: UUID
    company_id: Optional[UUID] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    data: Optional[dict] = None
    exp: int
    type: str


class TokenType(str, Enum):
    ACCESS = 'access'
    REFRESH = 'refresh'
    TEMPORARY = 'temporary'


class JWTManager:
    @classmethod
    def create(
            cls,
            sub: UUID,
            token_type: TokenType,
            company_id: Optional[UUID] = None,
            role: Optional[str] = None,
            permissions: Optional[List[str]] = None,
            data: dict = None,
            duration: timedelta = timedelta(minutes=30)
    ) -> str:
        """
        Create JWT token with multi-tenant support

        Args:
            sub: User ID
            token_type: Type of token (access, refresh, temporary)
            company_id: Company ID for multi-tenant isolation
            role: User role (owner, company_admin, etc.)
            permissions: List of permissions (e.g., ["leads.read", "calls.make"])
            data: Additional data to include in token
            duration: Token expiration duration

        Returns:
            Encoded JWT token string
        """
        now = datetime.now(timezone.utc)
        exp_time = now + duration
        payload = {
            "sub": str(sub),
            "company_id": str(company_id) if company_id else None,
            "role": role,
            "permissions": permissions or [],
            "data": data,
            "exp": int(exp_time.timestamp()),
            "type": token_type.value
        }
        return jwt.encode(payload, config.JWTConfig.SIGNING_KEY, algorithm=config.JWTConfig.ALGORITHM)

    @classmethod
    def verify(cls, token: str, expected_type: Optional[str] = None) -> JWTPayload | None:
        try:
            options, algorithms = {"verify_sub": False}, [config.JWTConfig.ALGORITHM]
            payload = jwt.decode(token, config.JWTConfig.SIGNING_KEY, algorithms, options)
        except ExpiredSignatureError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired or invalid.")
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.")

        if expected_type and payload.get("type") != expected_type:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token type mismatch.")
        return JWTPayload(**payload)

    @classmethod
    def generate_credentials(
            cls,
            sub: UUID,
            company_id: Optional[UUID] = None,
            role: Optional[str] = None,
            permissions: Optional[List[str]] = None,
            data: dict = None,
            access_duration=timedelta(minutes=30),
            refresh_duration=timedelta(days=30)
    ) -> dict:
        """
        Generate access and refresh tokens with multi-tenant support

        Args:
            sub: User ID
            company_id: Company ID for multi-tenant isolation
            role: User role
            permissions: List of permissions
            data: Additional data to include
            access_duration: Access token expiration
            refresh_duration: Refresh token expiration

        Returns:
            Dictionary with 'access' and 'refresh' tokens
        """
        return {
            "access": JWTManager.create(sub, TokenType.ACCESS, company_id, role, permissions, data, access_duration),
            "refresh": JWTManager.create(sub, TokenType.REFRESH, company_id, role, permissions, data, refresh_duration),
        }
