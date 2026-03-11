"""
Invite token generation and validation service.

Generates XXXX-XXXX tokens with charset A-Z + 2-9 (excludes 0, O, 1, I, L).
Stores SHA-256 hash of the stripped, uppercased token.
"""

import hashlib
import secrets

# Charset: A-Z + 2-9, excluding ambiguous chars (0, O, 1, I, L)
TOKEN_CHARSET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TOKEN_LENGTH = 8  # 4+4 with dash separator


def generate_invite_token() -> str:
    """
    Generate an invite token in XXXX-XXXX format.

    Uses secrets.choice for cryptographic randomness.
    Charset: A-Z (minus O, I, L) + 2-9 (minus 0, 1) = 33 chars.
    Entropy: 33^8 ~ 1.4 trillion combinations.

    Returns:
        Plaintext token string like "A3B7-K9M2"
    """
    chars = [secrets.choice(TOKEN_CHARSET) for _ in range(TOKEN_LENGTH)]
    return "".join(chars[:4]) + "-" + "".join(chars[4:])


def hash_token(token: str) -> str:
    """
    Hash a token (invite code or OTP) with SHA-256.

    For invite tokens: strip dash and uppercase before hashing.
    For OTPs: hash the raw string directly.

    Args:
        token: The plaintext token string

    Returns:
        SHA-256 hex digest (64 chars)
    """
    return hashlib.sha256(token.encode()).hexdigest()


def hash_invite_token(raw_token: str) -> str:
    """
    Hash an invite token after stripping dash and uppercasing.

    Args:
        raw_token: Plaintext token like "A3B7-K9M2"

    Returns:
        SHA-256 hex digest of "A3B7K9M2"
    """
    cleaned = raw_token.replace("-", "").upper()
    return hash_token(cleaned)


def generate_otp() -> str:
    """
    Generate a 6-digit OTP.

    Uses secrets.randbelow for cryptographic randomness.
    Leading zeros are valid (e.g., "042918").

    Returns:
        6-digit string zero-padded (e.g., "042918")
    """
    return f"{secrets.randbelow(1_000_000):06d}"
