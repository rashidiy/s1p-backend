from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel
from starlette import status

from core import config


class JWTPayload(BaseModel):
    sub: UUID
    data: Optional[dict]
    exp: int
    type: str


class TokenType(str, Enum):
    ACCESS = 'access'
    REFRESH = 'refresh'
    TEMPORARY = 'temporary'


class JWTManager:
    @classmethod
    def create(
            cls, sub: UUID, token_type: TokenType, data: dict = None, duration: timedelta = timedelta(minutes=30)
    ) -> str:
        now = datetime.now(timezone.utc)
        exp_time = now + duration
        payload = {"sub": str(sub), "data": data, "exp": int(exp_time.timestamp()), "type": token_type.value}
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
            data: dict = None,
            access_duration=timedelta(minutes=30),
            refresh_duration=timedelta(days=30)
    ) -> dict:
        return {
            "access": JWTManager.create(sub, TokenType.ACCESS, data, access_duration),
            "refresh": JWTManager.create(sub, TokenType.REFRESH, data, refresh_duration),
        }
