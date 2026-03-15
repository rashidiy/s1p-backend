"""
HMAC-SHA256 signed URL service — generates and verifies time-limited signed URLs.

Used for recording delivery in Telegram notifications.
Dual-auth: signed token (24h) OR JWT cookie (for logged-in CRM users).
"""

import hashlib
import hmac
import time
from typing import Optional

from core.config import SignedUrlConfig


def generate_signed_url(
    base_url: str,
    call_id: str,
    company_id: str,
    expiry_seconds: int | None = None,
) -> str:
    """
    Generate a signed recording URL.

    URL format: {base_url}?cid={company_id}&exp={expiry_ts}&sig={hmac_signature}
    """
    exp = int(time.time()) + (expiry_seconds or SignedUrlConfig.DEFAULT_EXPIRY)
    payload = f"{call_id}:{company_id}:{exp}"
    sig = hmac.new(
        SignedUrlConfig.SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{base_url}?cid={company_id}&exp={exp}&sig={sig}"


def verify_signature(
    call_id: str,
    company_id: str,
    exp: str,
    sig: str,
) -> tuple[bool, Optional[str]]:
    """
    Verify a signed URL's HMAC signature and expiry.

    Returns: (is_valid, error_message)
    """
    try:
        exp_int = int(exp)
    except (ValueError, TypeError):
        return False, "Invalid expiry"

    if time.time() > exp_int:
        return False, "Link expired"

    payload = f"{call_id}:{company_id}:{exp}"
    expected_sig = hmac.new(
        SignedUrlConfig.SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return False, "Invalid signature"

    return True, None
