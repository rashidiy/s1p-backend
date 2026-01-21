import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def required_env(s: str, default: str = None) -> Any:
    value = os.getenv(s, default)
    if value is None:
        raise RuntimeError(f"Required environment variable {s} not set.")
    return value


class DatabaseConfig:
    POSTGRES_HOST = required_env('POSTGRES_HOST')
    POSTGRES_PORT = required_env('POSTGRES_PORT')
    POSTGRES_DB = required_env('POSTGRES_DB')
    POSTGRES_USER = required_env('POSTGRES_USER')
    POSTGRES_PASSWORD = required_env('POSTGRES_PASSWORD')

    @classmethod
    def url(cls) -> str:
        return f"postgresql+asyncpg://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"


class JWTConfig:
    ALGORITHM = required_env('JWT_ALGORITHM', 'HS256')
    SIGNING_KEY = required_env('JWT_SIGNING_KEY')
