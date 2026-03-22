"""
Telegram webhook endpoint for receiving bot updates

This endpoint receives all Telegram bot updates:
- Callback queries from inline keyboard buttons
- Messages including /start and /register commands for auth flows
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from fastapi import APIRouter, Request, HTTPException, status, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import AppConfig, TelegramConfig
from db import get_session
from db.models.telegram_config import TelegramBotConfig
from db.models.telegram_auth_challenge import TelegramAuthChallenge
from db.models.lead import Lead
from db.models.user import User
from utils.services.invite_token_service import generate_otp, hash_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/telegram", tags=["Telegram Webhook"])

limiter = Limiter(key_func=get_remote_address)


# ── Bot instance for sending messages ─────────────────────────────────

def _get_bot() -> Bot | None:
    """Get an aiogram Bot instance for sending messages."""
    if not TelegramConfig.BOT_TOKEN:
        return None
    return Bot(token=TelegramConfig.BOT_TOKEN)


# ── Redis helpers for OTP rate limiting ──────────────────────────────

async def _get_redis():
    """Get Redis client for OTP rate limiting."""
    try:
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    except Exception:
        return None


async def _check_otp_rate_limit(user_id: str) -> bool:
    """Check if an OTP was sent for this user in the last 60 seconds."""
    client = await _get_redis()
    if not client:
        return False
    try:
        val = await client.get(f"otp_rate:{user_id}")
        return val is not None
    finally:
        await client.aclose()


async def _set_otp_rate_limit(user_id: str) -> None:
    """Set OTP rate limit key (60s TTL)."""
    client = await _get_redis()
    if not client:
        return
    try:
        await client.setex(f"otp_rate:{user_id}", 60, "1")
    finally:
        await client.aclose()


async def _check_otp_lockout(user_id: str) -> bool:
    """Check if user is locked out from OTP verification."""
    client = await _get_redis()
    if not client:
        return False
    try:
        val = await client.get(f"otp_lockout:{user_id}")
        return val is not None
    finally:
        await client.aclose()


# ── Webhook endpoint ─────────────────────────────────────────────────

@router.post("/{secret}")
@limiter.limit("120/minute")
async def telegram_webhook(
    secret: str,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Receive Telegram bot updates.

    Handles:
    - Callback queries (inline button presses)
    - Messages (/start, /register commands for auth flows)

    The secret path parameter validates the webhook is from our bot setup.
    """
    # Validate webhook secret
    if not TelegramConfig.WEBHOOK_SECRET or secret != TelegramConfig.WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret"
        )

    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    # Handle callback queries (button presses)
    callback_query = data.get("callback_query")
    if callback_query:
        await _handle_callback_query(callback_query, session)

    # Handle messages (commands)
    message = data.get("message")
    if message:
        await _handle_message(message, session)

    # Always return 200 to Telegram
    return {"ok": True}


# ── Message handlers ─────────────────────────────────────────────────

async def _handle_message(message: dict, session: AsyncSession):
    """Route incoming messages to the appropriate handler."""
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")

    if not text or not chat_id or not telegram_user_id:
        return

    try:
        if text.startswith("/start"):
            parts = text.strip().split(maxsplit=1)
            payload = parts[1] if len(parts) > 1 else ""

            if payload.startswith("login_"):
                await _handle_login_start(chat_id, telegram_user_id, payload, session)
            elif payload.startswith("reg_"):
                await _handle_register_start(chat_id, telegram_user_id, from_user, payload, session)
            else:
                # Default /start — show Chat ID
                await _send_message(
                    chat_id,
                    f"S1P CRM Bot connected!\n\n"
                    f"Your Chat ID: {chat_id}\n\n"
                    f"Copy this Chat ID and paste it in Settings > Telegram "
                    f"in the CRM to start receiving notifications."
                )

        elif text.startswith("/register"):
            await _handle_register(chat_id, telegram_user_id, session)

        elif text.startswith("/today"):
            await _handle_today_command(chat_id, session)

        elif text.startswith("/search"):
            query = text[len("/search"):].strip()
            await _handle_search_command(chat_id, query, session)

        elif text.startswith("/myleads"):
            await _handle_myleads_command(chat_id, telegram_user_id, session)

    except Exception:
        logger.exception("Error handling message from Telegram user %s", telegram_user_id)


async def _handle_login_start(
    chat_id: int,
    telegram_user_id: int,
    payload: str,
    session: AsyncSession,
) -> None:
    """
    Handle /start login_{CHALLENGE_ID} deep link.

    1. Parse challenge ID
    2. Look up challenge (login, not expired, not used)
    3. Find user by telegram_user_id + company_id
    4. Generate OTP, hash it, store in challenge
    5. Send OTP to user via Telegram DM
    """
    challenge_id = payload[len("login_"):]
    now = datetime.now(timezone.utc)

    # Look up challenge
    challenge = await session.get(TelegramAuthChallenge, challenge_id)

    if (
        not challenge
        or challenge.purpose != "login"
        or challenge.used
    ):
        await _send_message(
            chat_id,
            "This login link has expired. Please request a new one from the login page."
        )
        return

    if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        await _send_message(
            chat_id,
            "This login link has expired. Please request a new one from the login page."
        )
        return

    # Find user by telegram_user_id + company_id
    user = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=challenge.company_id,
    )
    if not user or user.deleted_at is not None:
        await _send_message(
            chat_id,
            "No account found for this Telegram account in this company."
        )
        return

    if not user.is_active or user.is_suspended:
        await _send_message(
            chat_id,
            "Your account is suspended. Contact your administrator."
        )
        return

    # Check OTP rate limit (1 per 60 seconds per user)
    if await _check_otp_rate_limit(str(user.id)):
        await _send_message(
            chat_id,
            "Please wait before requesting another code."
        )
        return

    # Check lockout
    if await _check_otp_lockout(str(user.id)):
        await _send_message(
            chat_id,
            "Account temporarily locked. Try again later."
        )
        return

    # Generate OTP
    otp = generate_otp()
    otp_hashed = hash_token(otp)

    # Update challenge
    challenge.telegram_user_id = telegram_user_id
    challenge.user_id = user.id
    challenge.otp_hash = otp_hashed
    challenge.expires_at = now + timedelta(minutes=5)

    await session.commit()

    # Set rate limit
    await _set_otp_rate_limit(str(user.id))

    # Update Telegram avatar if user hasn't uploaded a custom one
    if not user.avatar_is_custom:
        try:
            bot = _get_bot()
            if bot:
                try:
                    photos = await bot.get_user_profile_photos(user_id=telegram_user_id, limit=1)
                    if photos.total_count > 0 and photos.photos:
                        photo = photos.photos[0][-1]
                        from utils.services.avatar_service import download_telegram_avatar
                        filename = await download_telegram_avatar(str(user.id), telegram_user_id)
                        if filename:
                            user.avatar = filename
                            user.telegram_avatar_file_id = photo.file_id
                            await session.commit()
                finally:
                    await bot.session.close()
        except Exception:
            logger.warning("Failed to update avatar during login for user %s", user.id)

    # Send OTP to user (monospace format for tap-to-copy)
    await _send_message(
        chat_id,
        f"Your login code:\n\n`{otp}`\n\n"
        f"Tap the code to copy\\. Expires in 5 minutes\\.",
        parse_mode="MarkdownV2",
    )


async def _handle_register_start(
    chat_id: int,
    telegram_user_id: int,
    from_user: dict,
    payload: str,
    session: AsyncSession,
) -> None:
    """
    Handle /start reg_{CHALLENGE_ID} deep link.

    Captures Telegram profile data and stores it in the challenge
    so the registration page can complete the flow.
    """
    challenge_id = payload[len("reg_"):]
    now = datetime.now(timezone.utc)

    challenge = await session.get(TelegramAuthChallenge, challenge_id)

    if not challenge or challenge.purpose != "register":
        await _send_message(chat_id, "This link is invalid.")
        return

    if challenge.used:
        await _send_message(chat_id, "This link has already been used.")
        return

    if challenge.expires_at.replace(tzinfo=timezone.utc) < now:
        await _send_message(chat_id, "This link has expired.")
        return

    # Check if telegram user already registered in this company
    existing = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=challenge.company_id,
    )
    if existing:
        await _send_message(
            chat_id,
            "This Telegram account is already registered in this company."
        )
        return

    # Capture telegram profile data
    telegram_data = {
        "first_name": from_user.get("first_name"),
        "last_name": from_user.get("last_name"),
        "username": from_user.get("username"),
    }

    # Try to get profile photo
    try:
        bot = _get_bot()
        if bot:
            photos = await bot.get_user_profile_photos(user_id=telegram_user_id, limit=1)
            if photos.total_count > 0 and photos.photos:
                photo = photos.photos[0][-1]
                telegram_data["avatar_file_id"] = photo.file_id
            await bot.session.close()
    except Exception:
        logger.warning("Could not fetch profile photo for user %s", telegram_user_id)

    # Update challenge with Telegram data
    challenge.telegram_user_id = telegram_user_id
    challenge.telegram_data = telegram_data
    await session.commit()

    # Get company name for confirmation message
    from db.models.company import Company
    company = await session.get(Company, challenge.company_id)
    company_name = company.name if company else "the company"

    await _send_message(
        chat_id,
        f"Telegram connected!\n\n"
        f"Return to the {company_name} registration page to complete signup."
    )


async def _handle_register(
    chat_id: int,
    telegram_user_id: int,
    session: AsyncSession,
) -> None:
    """
    Handle /register command.

    Creates a registration challenge and sends the user a link
    to the registration page on the website.
    """
    now = datetime.now(timezone.utc)
    challenge_id = secrets.token_urlsafe(16)

    challenge = TelegramAuthChallenge(
        id=challenge_id,
        company_id=None,  # Resolved from invite token at registration
        purpose="register",
        telegram_user_id=telegram_user_id,
        expires_at=now + timedelta(minutes=10),
    )
    session.add(challenge)
    await session.commit()

    # Build registration link
    base_url = AppConfig.FRONTEND_URL.rstrip("/")
    reg_url = f"{base_url}/register?s={challenge_id}"

    await _send_message(
        chat_id,
        f"To complete registration, open this link and enter your invite code:\n\n"
        f"{reg_url}"
    )


# ── Send message helper ──────────────────────────────────────────────

async def _send_message(chat_id: int, text: str, parse_mode: str | None = None) -> None:
    """Send a message to a Telegram chat."""
    bot = _get_bot()
    if not bot:
        return

    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except Exception:
        logger.exception("Failed to send Telegram message to chat %s", chat_id)
    finally:
        await bot.session.close()


# ── Bot commands (/today, /search, /myleads) ─────────────────────────

async def _get_config_by_chat(chat_id: int, session: AsyncSession):
    """Find TelegramBotConfig by chat_id or group_chat_id."""
    from sqlalchemy import or_
    result = await session.execute(
        select(TelegramBotConfig).where(
            or_(
                TelegramBotConfig.chat_id == str(chat_id),
                TelegramBotConfig.group_chat_id == chat_id,
            ),
            TelegramBotConfig.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _handle_today_command(chat_id: int, session: AsyncSession):
    """Handle /today — show today's stats for the company."""
    from datetime import date, datetime, timezone
    from utils.services.analytics_service import AnalyticsService
    from utils.services.telegram_i18n import no_data_text

    config = await _get_config_by_chat(chat_id, session)
    if not config:
        await _send_message(chat_id, "Bot not configured for this chat")
        return

    lang = config.language or "ru"
    today = date.today()
    start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

    try:
        call_stats = await AnalyticsService.get_call_stats(
            session=session,
            company_id=config.company_id,
            date_from=start,
            date_to=end,
        )
        lead_stats = await AnalyticsService.get_lead_stats(
            session=session,
            company_id=config.company_id,
            date_from=start,
            date_to=end,
        )

        from utils.services.telegram_i18n import daily_digest_message
        text = daily_digest_message(
            date=today.isoformat(),
            total_calls=call_stats.total_calls if call_stats else 0,
            missed_calls=call_stats.missed_calls if call_stats else 0,
            avg_duration_sec=int(call_stats.average_duration) if call_stats and call_stats.average_duration else 0,
            new_leads=lead_stats.total_leads if lead_stats else 0,
            deals_won=0,
            deals_lost=0,
            lang=lang,
        )
        await _send_message(chat_id, text)

    except Exception:
        logger.exception("Error in /today command for chat %s", chat_id)
        await _send_message(chat_id, no_data_text(lang))


async def _handle_search_command(chat_id: int, query: str, session: AsyncSession):
    """Handle /search {query} — search contacts by phone/name."""
    from db.models.contact import Contact
    from utils.services.telegram_i18n import search_header, no_data_text

    if not query:
        await _send_message(chat_id, "Usage: /search <phone or name>")
        return

    config = await _get_config_by_chat(chat_id, session)
    if not config:
        await _send_message(chat_id, "Bot not configured for this chat")
        return

    lang = config.language or "ru"

    from sqlalchemy import or_
    results = await session.execute(
        select(Contact)
        .where(
            Contact.company_id == config.company_id,
            Contact.deleted_at.is_(None),
            or_(
                Contact.phone.ilike(f"%{query}%"),
                Contact.first_name.ilike(f"%{query}%"),
                Contact.last_name.ilike(f"%{query}%"),
            ),
        )
        .limit(5)
    )
    contacts = results.scalars().all()

    if not contacts:
        await _send_message(chat_id, no_data_text(lang))
        return

    header = search_header(query, lang)
    lines = [header, ""]
    for c in contacts:
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or "—"
        phone = c.phone or "—"
        lines.append(f"• {name} — {phone}")

    await _send_message(chat_id, "\n".join(lines))


async def _handle_myleads_command(chat_id: int, telegram_user_id: int, session: AsyncSession):
    """Handle /myleads — show leads assigned to the user."""
    from utils.services.telegram_i18n import my_leads_header, no_data_text

    config = await _get_config_by_chat(chat_id, session)
    if not config:
        await _send_message(chat_id, "Bot not configured for this chat")
        return

    lang = config.language or "ru"

    # Find CRM user by telegram_user_id
    user = await User.get(
        session=session,
        telegram_user_id=telegram_user_id,
        company_id=config.company_id,
    )
    if not user:
        from utils.services.telegram_i18n import link_telegram_text
        await _send_message(chat_id, link_telegram_text(lang))
        return

    results = await session.execute(
        select(Lead)
        .where(
            Lead.company_id == config.company_id,
            Lead.assigned_to == user.id,
            Lead.deleted_at.is_(None),
            Lead.status.notin_(["converted", "lost"]),
        )
        .limit(10)
    )
    leads = results.scalars().all()

    if not leads:
        await _send_message(chat_id, no_data_text(lang))
        return

    header = my_leads_header(lang)
    lines = [header, ""]
    for lead in leads:
        title = lead.title or "—"
        status_val = lead.status if isinstance(lead.status, str) else (lead.status.value if lead.status else "—")
        lines.append(f"• {title} [{status_val}]")

    await _send_message(chat_id, "\n".join(lines))


# ── Callback query handlers (V2 — shortened prefixes) ────────────────
#
# Callback data format: "prefix:param" (must fit 64 bytes)
# Prefixes: mh=mark_handled, al=assign_lead, cb=callback, cc=create_contact

async def _find_crm_user(telegram_user_id: int, chat_id: str, session: AsyncSession) -> User | None:
    """Find a CRM user by telegram_user_id in any company linked to this chat."""
    from sqlalchemy import or_
    # Find configs matching this chat
    config_q = await session.execute(
        select(TelegramBotConfig.company_id).where(
            or_(
                TelegramBotConfig.chat_id == chat_id,
                TelegramBotConfig.group_chat_id == int(chat_id) if chat_id.lstrip('-').isdigit() else False,
            ),
            TelegramBotConfig.deleted_at.is_(None),
        )
    )
    company_ids = [row[0] for row in config_q.all()]

    for cid in company_ids:
        user = await User.get(
            session=session,
            telegram_user_id=telegram_user_id,
            company_id=cid,
        )
        if user and not user.deleted_at:
            return user
    return None


async def _get_config_for_chat(chat_id: str, session: AsyncSession) -> TelegramBotConfig | None:
    """Find TelegramBotConfig for a chat (legacy chat_id OR V2 group_chat_id)."""
    from sqlalchemy import or_

    conditions = [TelegramBotConfig.chat_id == chat_id]
    if chat_id.lstrip('-').isdigit():
        conditions.append(TelegramBotConfig.group_chat_id == int(chat_id))

    result = await session.execute(
        select(TelegramBotConfig).where(
            or_(*conditions),
            TelegramBotConfig.enabled.is_(True),
            TelegramBotConfig.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _handle_callback_query(callback_query: dict, session: AsyncSession):
    """Process inline button callback queries (V2 shortened prefixes)."""
    callback_data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    message_id = message.get("message_id")
    callback_query_id = callback_query.get("id")
    user_info = callback_query.get("from", {})
    telegram_user_id = user_info.get("id")
    user_display = user_info.get("first_name") or user_info.get("username") or "Unknown"

    if not callback_data or not chat_id:
        return

    config = await _get_config_for_chat(chat_id, session)
    if not config:
        await _answer_callback(callback_query_id, "Bot not configured for this chat")
        return

    lang = config.language or "ru"

    # Parse: "prefix:param"
    parts = callback_data.split(":", 1)
    action = parts[0]
    param = parts[1] if len(parts) > 1 else ""

    # Validate param as UUID for actions that use it as a DB identifier
    if action in ("al",) and param:
        try:
            from uuid import UUID as _UUID
            _UUID(param)
        except ValueError:
            return

    try:
        if action == "mh":
            # Mark handled — react + edit message to add handler name, remove buttons
            from utils.services.telegram_i18n import handled_text
            from utils.services.telegram_service import TelegramService
            suffix = handled_text(user_display, lang)
            await TelegramService.react_to_message(chat_id, message_id, "✅")
            await _edit_message_handled(chat_id, message_id, message.get("text", ""), suffix)
            await _answer_callback(callback_query_id, suffix)

        elif action == "al":
            # Assign lead — find CRM user, assign lead
            from utils.services.telegram_i18n import lead_assigned_text, link_telegram_text

            crm_user = await _find_crm_user(telegram_user_id, chat_id, session) if telegram_user_id else None
            if not crm_user:
                await _answer_callback(callback_query_id, link_telegram_text(lang))
                return

            lead = await Lead.get(session=session, id=param, company_id=config.company_id)
            if lead:
                lead.assigned_to = crm_user.id
                await session.commit()
                msg = lead_assigned_text(crm_user.full_name, lang)
                from utils.services.telegram_service import TelegramService
                await TelegramService.react_to_message(chat_id, message_id, "👤")
                await _answer_callback(callback_query_id, msg)
                logger.info("Lead %s assigned to %s via Telegram", param, crm_user.id)
            else:
                await _answer_callback(callback_query_id, "Lead not found")

        elif action == "cb":
            # Callback — show phone number (Phase 1, no telephony integration)
            await _answer_callback(callback_query_id, f"Call: {param}")

        elif action == "cc":
            # Create contact from phone
            from utils.services.telegram_i18n import contact_created_text, link_telegram_text
            from db.models.contact import Contact

            crm_user = await _find_crm_user(telegram_user_id, chat_id, session) if telegram_user_id else None
            if not crm_user:
                await _answer_callback(callback_query_id, link_telegram_text(lang))
                return

            # Check if contact already exists
            existing = await session.execute(
                select(Contact.id).where(
                    Contact.company_id == config.company_id,
                    Contact.phone == param,
                    Contact.deleted_at.is_(None),
                ).limit(1)
            )
            if existing.first():
                await _answer_callback(callback_query_id, "Contact already exists")
                return

            contact = await Contact.create(
                session=session,
                company_id=config.company_id,
                phone=param,
                first_name=param,  # Phone as placeholder name
                created_by=crm_user.id,
            )
            msg = contact_created_text(param, lang)
            await _answer_callback(callback_query_id, msg)
            logger.info("Contact created for %s by %s via Telegram", param, crm_user.id)

        # Legacy prefixes (backward compat for messages sent before V2)
        elif action == "mark_handled":
            await _answer_callback(callback_query_id, "Marked as handled")
        elif action == "assign_lead":
            await _answer_callback(callback_query_id, "Use CRM to assign leads")
        elif action == "callback":
            await _answer_callback(callback_query_id, f"Call: {param}")

        else:
            await _answer_callback(callback_query_id, "Unknown action")

    except Exception as e:
        logger.error("Error handling callback %s: %s", action, e, exc_info=True)
        await _answer_callback(callback_query_id, "Error processing request")


async def _edit_message_handled(chat_id: str, message_id: int, original_text: str, suffix: str):
    """Edit the original message to append 'Handled by X' and remove inline keyboard."""
    bot = _get_bot()
    if not bot or not message_id:
        return

    try:
        from aiogram.enums import ParseMode
        new_text = f"{original_text}\n\n✅ {suffix}"
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception:
        logger.warning("Could not edit message %s in chat %s", message_id, chat_id)
    finally:
        await bot.session.close()


async def _answer_callback(callback_query_id: str, text: str):
    """Answer a Telegram callback query."""
    bot = _get_bot()
    if not bot:
        return

    try:
        await bot.answer_callback_query(callback_query_id=callback_query_id, text=text)
    except Exception as e:
        logger.error("Failed to answer callback query: %s", e, exc_info=True)
    finally:
        await bot.session.close()
