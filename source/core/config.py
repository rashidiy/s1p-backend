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


class AppConfig:
    """Application configuration"""
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')


class WebhookConfig:
    """Webhook security configuration"""
    # IP whitelisting for webhook endpoints
    SIPUNI_ALLOWED_IPS = os.getenv('SIPUNI_ALLOWED_IPS', '').split(',') if os.getenv('SIPUNI_ALLOWED_IPS') else []
    BINOTEL_ALLOWED_IPS = os.getenv('BINOTEL_ALLOWED_IPS', '').split(',') if os.getenv('BINOTEL_ALLOWED_IPS') else []

    # Fallback: allow all IPs if not configured (dev mode)
    WEBHOOK_IP_WHITELIST_ENABLED = os.getenv('WEBHOOK_IP_WHITELIST_ENABLED', 'false').lower() == 'true'

    # Record proxy settings
    RECORD_PROXY_SECRET = os.getenv('RECORD_PROXY_SECRET', '')
    RECORD_PROXY_TOKEN_EXPIRY = int(os.getenv('RECORD_PROXY_TOKEN_EXPIRY', '86400'))  # 24 hours
