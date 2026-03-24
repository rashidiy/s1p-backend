"""
Telegram Mini App startapp parameter encoding/decoding.

Encodes action + data + company_id into a signed, URL-safe string
for use in t.me/bot/app?startapp=PARAM deep links.

Format: base64url(action:data:company_id:signature)
Signature: HMAC-SHA256 of "action:data:company_id" with bot token as key.
"""

import base64
import hashlib
import hmac

from core.config import TelegramConfig


def _sign(payload: str) -> str:
    """Generate short HMAC signature (first 8 chars)."""
    sig = hmac.new(
        TelegramConfig.BOT_TOKEN.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:8]
    return sig


def encode_startapp(action: str, data: str, company_id: str) -> str:
    """
    Encode a startapp parameter with signature.

    Returns a base64url string safe for Telegram's startapp param
    (alphanumeric, _, -, max 512 chars).
    """
    payload = f"{action}:{data}:{company_id}"
    sig = _sign(payload)
    raw = f"{payload}:{sig}"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    return encoded


def decode_startapp(param: str) -> dict | None:
    """
    Decode and verify a startapp parameter.

    Returns {"action": ..., "data": ..., "company_id": ...} or None if invalid.
    """
    try:
        # Restore base64 padding
        padded = param + "=" * (-len(param) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        parts = raw.split(":")
        if len(parts) != 4:
            return None

        action, data, company_id, sig = parts
        payload = f"{action}:{data}:{company_id}"
        expected_sig = _sign(payload)
        if not hmac.compare_digest(sig, expected_sig):
            return None

        return {"action": action, "data": data, "company_id": company_id}
    except Exception:
        return None


def build_miniapp_url(action: str, data: str, company_id: str) -> str:
    """Build a full t.me deep link for Mini App with signed params."""
    param = encode_startapp(action, data, company_id)
    bot_username = TelegramConfig.BOT_USERNAME
    return f"https://t.me/{bot_username}/app?startapp={param}"
