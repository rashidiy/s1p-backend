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
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')


class SMTPConfig:
    """SMTP email configuration"""
    HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    PORT = int(os.getenv('SMTP_PORT', '587'))
    USER = os.getenv('SMTP_USER', '')
    PASSWORD = os.getenv('SMTP_PASSWORD', '')
    FROM_NAME = os.getenv('SMTP_FROM_NAME', 'S1P CRM')
    FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', '')
    USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    ENABLED = os.getenv('SMTP_ENABLED', 'false').lower() == 'true'


class TelegramConfig:
    """Telegram bot configuration"""
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
    ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
    BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', 's1pcrm_bot')


class WebhookConfig:
    """Webhook security configuration"""
    # IP whitelisting for webhook endpoints
    SIPUNI_ALLOWED_IPS = os.getenv('SIPUNI_ALLOWED_IPS', '').split(',') if os.getenv('SIPUNI_ALLOWED_IPS') else []
    BINOTEL_ALLOWED_IPS = os.getenv('BINOTEL_ALLOWED_IPS', '').split(',') if os.getenv('BINOTEL_ALLOWED_IPS') else []

    # IP whitelisting enabled by default (fail-closed); set to 'false' to disable
    WEBHOOK_IP_WHITELIST_ENABLED = os.getenv('WEBHOOK_IP_WHITELIST_ENABLED', 'true').lower() == 'true'

