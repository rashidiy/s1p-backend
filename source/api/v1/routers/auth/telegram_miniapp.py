"""
Telegram Mini App auth — validate initData HMAC → issue JWT.

Validates the Telegram Mini App launch data using HMAC-SHA256
(per Telegram's Web App authentication protocol) and maps
telegram_user_id to a CRM user, issuing JWT credentials.
"""

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from core.config import TelegramConfig
from db import get_session
from db.models.user import User
from utils.managers import JWTManager
from api.v1.routers.auth import router

logger = logging.getLogger(__name__)


class MiniAppAuthRequest(BaseModel):
    """Mini App auth request — raw initData string from Telegram."""
    init_data: str
    company_id: UUID  # Which company to authenticate against


class MiniAppAuthResponse(BaseModel):
    """Mini App auth response — JWT credentials."""
    access_token: str
    refresh_token: str
    user_id: str
    first_name: str
    last_name: str | None = None


class MiniAppCompaniesRequest(BaseModel):
    """Request to list companies a Telegram user belongs to."""
    init_data: str


class MiniAppCompanyItem(BaseModel):
    """Company info for Mini App company picker."""
    id: str
    name: str
    role: str | None = None


def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Validate Telegram Mini App initData using HMAC-SHA256.

    Per Telegram docs:
    1. Parse initData as query string
    2. Sort all params except 'hash' alphabetically
    3. Build data_check_string: "key=value\nkey=value\n..."
    4. secret_key = HMAC-SHA256(bot_token, "WebAppData")
    5. hash = HMAC-SHA256(secret_key, data_check_string)
    6. Compare with 'hash' param

    Returns parsed user dict on success, None on failure.
    """
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)

        # Extract hash
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Build data_check_string (all params except hash, sorted)
        check_pairs = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            # parse_qs returns lists; take first value
            value = parsed[key][0] if parsed[key] else ""
            check_pairs.append(f"{key}={value}")

        data_check_string = "\n".join(check_pairs)

        # Calculate HMAC
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        # Parse user data
        user_str = parsed.get("user", [None])[0]
        if not user_str:
            return None

        return json.loads(user_str)

    except Exception:
        logger.debug("initData validation failed", exc_info=True)
        return None


@router.post("/telegram/miniapp", response_model=MiniAppAuthResponse)
async def miniapp_auth(
    data: MiniAppAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticate a Telegram Mini App user.

    Validates initData HMAC → maps telegram_user_id to CRM user → issues JWT.
    """
    if not TelegramConfig.BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot not configured",
        )

    # Validate initData
    tg_user = _validate_init_data(data.init_data, TelegramConfig.BOT_TOKEN)
    if not tg_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData — HMAC verification failed",
        )

    telegram_user_id = tg_user.get("id")
    if not telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user ID in initData",
        )

    # Find CRM user by telegram_user_id + company_id
    user = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=data.company_id,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No CRM account linked to this Telegram account",
        )

    if not user.is_active or user.is_suspended or user.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or suspended",
        )

    # Issue JWT credentials
    credentials = JWTManager.generate_credentials(
        sub=user.id,
        company_id=user.company_id,
        role=user.role.value if user.role else None,
        permissions=user.permissions or [],
    )

    return MiniAppAuthResponse(
        access_token=credentials["access"],
        refresh_token=credentials["refresh"],
        user_id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
    )


@router.post("/telegram/miniapp/companies", response_model=list[MiniAppCompanyItem])
async def miniapp_companies(
    data: MiniAppCompaniesRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    List companies a Telegram user belongs to.

    Validates initData HMAC → finds all companies for this telegram_user_id.
    Used by the Mini App company picker when no company_id is provided.
    """
    if not TelegramConfig.BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot not configured",
        )

    tg_user = _validate_init_data(data.init_data, TelegramConfig.BOT_TOKEN)
    if not tg_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        )

    telegram_user_id = tg_user.get("id")
    if not telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user ID in initData",
        )

    # Find all active users with this telegram_user_id across companies
    from sqlalchemy import select as sa_select
    from db.models.company import Company

    result = await session.execute(
        sa_select(User.company_id, User.role, Company.name)
        .join(Company, User.company_id == Company.id)
        .where(
            User.telegram_user_id == telegram_user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            Company.is_active.is_(True),
        )
    )
    rows = result.all()

    return [
        MiniAppCompanyItem(
            id=str(row.company_id),
            name=row.name,
            role=row.role.value if row.role else None,
        )
        for row in rows
    ]
