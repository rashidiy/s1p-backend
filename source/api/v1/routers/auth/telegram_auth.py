"""
Telegram-based authentication endpoints.

Handles login via OTP (challenge -> deep link -> OTP -> verify)
and registration via invite token.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx

from fastapi import Depends, HTTPException, Request, Response
from fastapi import Response as FastAPIResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.v1.schemas import AuthSchema
from api.v1.schemas.telegram_auth import (
    ChallengeStatusResponse,
    LoginChallengeResponse,
    RegisterChallengeRequest,
    RegisterChallengeResponse,
    RegisterChallengeStatusResponse,
    TelegramRegisterRequest,
    VerifyOtpRequest,
)
from core.config import TelegramConfig
from db import get_session
from db.models import User
from db.models.invite_token import InviteToken
from db.models.telegram_auth_challenge import TelegramAuthChallenge
from utils.managers import JWTManager
from utils.services.invite_token_service import hash_invite_token, hash_token
from utils.services.telegram_service import get_bot
from . import router
from .auth import _extract_subdomain, _resolve_company, _set_auth_cookies

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

# Redis-based OTP lockout helpers (reuse lockout pattern)
OTP_LOCKOUT_THRESHOLD = 5
OTP_LOCKOUT_WINDOW = 900  # 15 minutes
OTP_LOCKOUT_DURATION = 1800  # 30 minutes


async def _get_redis():
    """Get Redis client for OTP rate limiting."""
    try:
        import redis.asyncio as aioredis
        import os
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    except Exception:
        return None


async def _check_otp_lockout(user_id: str) -> tuple[bool, int]:
    """
    Check if user is locked out from OTP verification.

    Returns:
        (is_locked, minutes_remaining)
    """
    client = await _get_redis()
    if not client:
        return False, 0

    lockout_key = f"otp_lockout:{user_id}"
    ttl = await client.ttl(lockout_key)
    if ttl > 0:
        return True, (ttl + 59) // 60  # round up to nearest minute
    return False, 0


async def _record_failed_otp(user_id: str) -> None:
    """Record a failed OTP verification attempt."""
    client = await _get_redis()
    if not client:
        return

    key = f"otp_failures:{user_id}"
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, OTP_LOCKOUT_WINDOW)

    if count >= OTP_LOCKOUT_THRESHOLD:
        await client.setex(f"otp_lockout:{user_id}", OTP_LOCKOUT_DURATION, "1")
        await client.delete(key)


async def _clear_otp_failures(user_id: str) -> None:
    """Clear OTP failure counter on successful verification."""
    client = await _get_redis()
    if not client:
        return
    await client.delete(f"otp_failures:{user_id}")


def _generate_credentials_for_user(user: User, response: Response) -> dict:
    """Generate JWT credentials for a user and set cookies."""
    credentials = JWTManager.generate_credentials(
        sub=user.id,
        company_id=user.company_id,
        role=user.role.value if user.role else None,
        permissions=user.permissions or [],
        access_duration=timedelta(hours=24),
        refresh_duration=timedelta(days=30),
    )
    _set_auth_cookies(response, credentials)
    return credentials


# ── Endpoint 4: Create Login Challenge ────────────────────────────────

@router.post('/telegram/login-challenge', response_model=LoginChallengeResponse)
@limiter.limit("10/minute")
async def create_login_challenge(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Create a Telegram login challenge.

    Returns a deep link for the user to open in Telegram.
    Company is resolved from Origin header (subdomain).
    """
    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    challenge_id = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    challenge = TelegramAuthChallenge(
        id=challenge_id,
        company_id=company.id,
        purpose="login",
        expires_at=expires_at,
    )
    session.add(challenge)
    await session.commit()

    bot_username = TelegramConfig.BOT_USERNAME
    deep_link = f"https://t.me/{bot_username}?start=login_{challenge_id}"

    return LoginChallengeResponse(
        challenge_id=challenge_id,
        deep_link=deep_link,
        expires_at=expires_at,
    )


# ── Endpoint 5: Poll Login Challenge Status ───────────────────────────

@router.get(
    '/telegram/login-challenge/{challenge_id}/status',
    response_model=ChallengeStatusResponse,
)
@limiter.limit("30/minute")
async def poll_challenge_status(
    challenge_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Poll the status of a login challenge.

    Frontend polls this to know when the OTP has been sent.
    """
    challenge = await session.get(TelegramAuthChallenge, challenge_id)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found",
        )

    now = datetime.now(timezone.utc)

    if challenge.used:
        challenge_status = "used"
    elif challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        challenge_status = "expired"
    elif challenge.otp_hash is not None:
        challenge_status = "otp_sent"
    else:
        challenge_status = "pending"

    return ChallengeStatusResponse(
        status=challenge_status,
        expires_at=challenge.expires_at,
    )


# ── Endpoint 6: Verify Login OTP ─────────────────────────────────────

@router.post('/telegram/verify-otp', response_model=AuthSchema.AuthorizedResponse)
@limiter.limit("5/minute")
async def verify_otp(
    data: VerifyOtpRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Verify the 6-digit OTP received via Telegram.

    On success, returns JWT credentials and sets httpOnly cookies.
    """
    subdomain = _extract_subdomain(request)
    company = await _resolve_company(subdomain, session)

    challenge = await session.get(TelegramAuthChallenge, data.challenge_id)
    now = datetime.now(timezone.utc)

    # Validate challenge existence and state
    if (
        not challenge
        or challenge.company_id != company.id
        or challenge.purpose != "login"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired challenge",
        )

    if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired challenge",
        )

    if challenge.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired challenge",
        )

    # OTP must have been sent (bot must have processed /start)
    if not challenge.telegram_user_id or not challenge.otp_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP not yet sent. Open the Telegram link first.",
        )

    # Max attempts check
    if challenge.attempts >= 3:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Too many attempts. Request a new code.",
        )

    # Check user-level lockout
    if challenge.user_id:
        is_locked, minutes_left = await _check_otp_lockout(str(challenge.user_id))
        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account temporarily locked. Try again in {minutes_left} minutes.",
            )

    # Verify OTP
    otp_hash = hash_token(data.otp)
    if otp_hash != challenge.otp_hash:
        challenge.attempts += 1
        await session.commit()

        if challenge.user_id:
            await _record_failed_otp(str(challenge.user_id))

        remaining = 3 - challenge.attempts
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Too many attempts. Request a new code.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid code. {remaining} attempts remaining.",
        )

    # OTP is correct — look up the user
    user = await User.get(
        session=session,
        id=challenge.user_id,
        company_id=company.id,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired challenge",
        )

    if not user.is_active or user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended",
        )

    # Mark challenge as used
    challenge.used = True
    await session.commit()

    # Clear OTP failure counter
    await _clear_otp_failures(str(user.id))

    # Generate credentials
    credentials = _generate_credentials_for_user(user, response)
    user.credentials = credentials
    user.must_change_password = False

    return user


# ── Endpoint 7: Create Register Challenge ─────────────────────────────

@router.post('/telegram/register-challenge', response_model=RegisterChallengeResponse)
@limiter.limit("10/minute")
async def create_register_challenge(
    data: RegisterChallengeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Validate an invite code and create a registration challenge.

    Returns a Telegram deep link for the user to connect their account.
    """
    now = datetime.now(timezone.utc)

    # Hash and look up invite token
    token_hash = hash_invite_token(data.invite_token)
    result = await session.execute(
        select(InviteToken).where(InviteToken.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite token",
        )
    if invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite token has already been used",
        )
    if invite.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite token",
        )

    # Get company name
    from db.models import Company
    company = await session.get(Company, invite.company_id)
    company_name = company.name if company else ""

    # Create registration challenge
    challenge_id = secrets.token_urlsafe(16)
    challenge = TelegramAuthChallenge(
        id=challenge_id,
        company_id=invite.company_id,
        purpose="register",
        invite_token_id=invite.id,
        expires_at=now + timedelta(minutes=10),
    )
    session.add(challenge)
    await session.commit()

    # Build deep link
    bot_username = TelegramConfig.BOT_USERNAME
    deep_link = f"https://t.me/{bot_username}?start=reg_{challenge_id}"

    return RegisterChallengeResponse(
        challenge_id=challenge_id,
        deep_link=deep_link,
        company_name=company_name,
        invite_first_name=invite.first_name,
        invite_last_name=invite.last_name,
        invite_phone=invite.phone,
    )


# ── Endpoint 7a: Poll Register Challenge Status ──────────────────────

@router.get(
    '/telegram/register-challenge/{challenge_id}/status',
    response_model=RegisterChallengeStatusResponse,
)
@limiter.limit("30/minute")
async def poll_register_challenge_status(
    challenge_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Poll the status of a registration challenge.

    Frontend polls this to know when the user has connected Telegram.
    """
    challenge = await session.get(TelegramAuthChallenge, challenge_id)
    if not challenge or challenge.purpose != "register":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found",
        )

    now = datetime.now(timezone.utc)

    if challenge.used:
        challenge_status = "used"
    elif challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        challenge_status = "expired"
    elif challenge.telegram_user_id:
        challenge_status = "telegram_connected"
    else:
        challenge_status = "pending"

    telegram_data = challenge.telegram_data or {}

    return RegisterChallengeStatusResponse(
        status=challenge_status,
        telegram_first_name=telegram_data.get("first_name"),
        telegram_last_name=telegram_data.get("last_name"),
        telegram_username=telegram_data.get("username"),
        has_avatar=bool(telegram_data.get("avatar_file_id")),
    )


# ── Endpoint 7b: Register Avatar ─────────────────────────────────────

@router.get('/telegram/avatar/{challenge_id}')
@limiter.limit("10/minute")
async def get_register_avatar(
    challenge_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Proxy endpoint to download user's Telegram avatar.
    """
    challenge = await session.get(TelegramAuthChallenge, challenge_id)
    now = datetime.now(timezone.utc)

    if (
        not challenge
        or challenge.purpose != "register"
        or challenge.used
        or challenge.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    telegram_data = challenge.telegram_data or {}
    file_id = telegram_data.get("avatar_file_id")
    if not file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar")

    # Get file path from Telegram
    bot = get_bot()
    if not bot:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bot unavailable")

    try:
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TelegramConfig.BOT_TOKEN}/{file.file_path}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()

            return FastAPIResponse(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar unavailable")


# ── Endpoint 8: Complete Registration ─────────────────────────────────

@router.post(
    '/telegram/register',
    response_model=AuthSchema.AuthorizedResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def telegram_register(
    data: TelegramRegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    Complete Telegram registration using an invite token.

    1. Validates the registration session (from bot /register command)
    2. Validates the invite token (XXXX-XXXX)
    3. Creates the user account
    4. Returns JWT credentials
    """
    now = datetime.now(timezone.utc)

    # 1. Look up registration challenge
    challenge = await session.get(TelegramAuthChallenge, data.session_id)
    if (
        not challenge
        or challenge.purpose != "register"
        or challenge.used
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired registration session",
        )

    if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired registration session",
        )

    # 2. Get telegram_user_id from challenge
    telegram_user_id = challenge.telegram_user_id
    if not telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired registration session",
        )

    # 3. Hash and look up invite token
    token_hash = hash_invite_token(data.invite_token)

    result = await session.execute(
        select(InviteToken).where(InviteToken.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite token",
        )

    if invite.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite token has already been used",
        )

    if invite.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invite token",
        )

    # 4. Check no existing user with this telegram_user_id
    existing_tg = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=invite.company_id,
    )
    if existing_tg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Telegram account is already registered",
        )

    # Get telegram data from challenge
    telegram_data = challenge.telegram_data or {}

    # Priority: user form > Telegram data > InviteToken data
    final_first_name = data.first_name or telegram_data.get("first_name") or invite.first_name or "User"
    final_last_name = data.last_name or telegram_data.get("last_name") or invite.last_name
    final_phone = data.phone or (invite.phone if invite.phone else "")

    # 5. Check no existing user with this phone + company_id
    final_phone_check = data.phone or invite.phone
    if final_phone_check:
        existing_phone = await User.get(
            session=session,
            phone=final_phone_check,
            company_id=invite.company_id,
        )
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this phone number already exists",
            )

    # 6. Create user
    from utils.permissions import ROLE_PERMISSIONS

    user = await User.create(
        session=session,
        first_name=final_first_name,
        last_name=final_last_name,
        phone=final_phone,
        company_id=invite.company_id,
        role=invite.role,
        permissions=invite.permissions if invite.permissions else ROLE_PERMISSIONS.get(invite.role, []),
        permission_group_id=invite.permission_group_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_data.get("username"),
        telegram_first_name=telegram_data.get("first_name"),
        telegram_last_name=telegram_data.get("last_name"),
        telegram_avatar_file_id=telegram_data.get("avatar_file_id"),
        email=None,
        password_hash=None,
        is_active=True,
        is_suspended=False,
        email_verified=True,
        commit=False,
    )

    # 7. Mark invite token as used
    invite.used_at = now
    invite.used_by = user.id

    # 8. Mark challenge as used
    challenge.used = True
    challenge.company_id = invite.company_id

    await session.commit()
    await session.refresh(user)

    # 8a. Download Telegram avatar if available and not skipped
    if telegram_data.get("avatar_file_id") and not data.skip_avatar:
        try:
            from utils.services.avatar_service import download_telegram_avatar
            filename = await download_telegram_avatar(str(user.id), telegram_user_id)
            if filename:
                user.avatar = filename
                await session.commit()
                await session.refresh(user)
        except Exception:
            logger.debug("Failed to download avatar during registration for user %s", user.id)

    # 9. Generate credentials
    credentials = _generate_credentials_for_user(user, response)
    user.credentials = credentials
    user.must_change_password = False

    return user
