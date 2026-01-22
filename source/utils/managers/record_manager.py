"""
Call Recording Proxy Manager
Generates signed tokens for secure access to call recordings
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
import hmac
import hashlib
import base64

from fastapi import HTTPException
from starlette import status

from core.config import WebhookConfig


class RecordTokenManager:
    """
    Manages signed tokens for call recording access

    Provides secure, time-limited access to call recordings without exposing
    provider URLs directly to clients.
    """

    @classmethod
    def generate_token(
            cls,
            call_id: UUID,
            company_id: UUID,
            expires_in: int = None
    ) -> str:
        """
        Generate a signed token for call recording access

        Args:
            call_id: The call event ID
            company_id: The company ID (for multi-tenant validation)
            expires_in: Token expiry in seconds (default: 24 hours)

        Returns:
            Base64-encoded signed token
        """
        if not WebhookConfig.RECORD_PROXY_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Record proxy not configured. Set RECORD_PROXY_SECRET."
            )

        expires_in = expires_in or WebhookConfig.RECORD_PROXY_TOKEN_EXPIRY
        exp_time = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        exp_timestamp = int(exp_time.timestamp())

        # Create token payload: call_id:company_id:exp_timestamp
        payload = f"{call_id}:{company_id}:{exp_timestamp}"

        # Generate HMAC signature
        signature = hmac.new(
            WebhookConfig.RECORD_PROXY_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).digest()

        # Combine payload and signature
        token_bytes = f"{payload}:".encode() + signature
        token = base64.urlsafe_b64encode(token_bytes).decode()

        return token

    @classmethod
    def validate_token(cls, token: str) -> dict:
        """
        Validate a signed token and extract call_id and company_id

        Args:
            token: Base64-encoded signed token

        Returns:
            Dictionary with call_id, company_id if valid

        Raises:
            HTTPException if token is invalid or expired
        """
        if not WebhookConfig.RECORD_PROXY_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Record proxy not configured"
            )

        try:
            # Decode token
            token_bytes = base64.urlsafe_b64decode(token.encode())

            # Split payload and signature
            parts = token_bytes.decode().rsplit(':', 1)
            if len(parts) != 2:
                raise ValueError("Invalid token format")

            payload, signature_b64 = parts
            signature_received = base64.b64decode(signature_b64.encode())

            # Parse payload
            call_id_str, company_id_str, exp_timestamp_str = payload.split(':')
            call_id = UUID(call_id_str)
            company_id = UUID(company_id_str)
            exp_timestamp = int(exp_timestamp_str)

            # Verify signature
            expected_signature = hmac.new(
                WebhookConfig.RECORD_PROXY_SECRET.encode(),
                payload.encode(),
                hashlib.sha256
            ).digest()

            if not hmac.compare_digest(signature_received, expected_signature):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid token signature"
                )

            # Check expiration
            now = int(datetime.now(timezone.utc).timestamp())
            if now > exp_timestamp:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Token expired"
                )

            return {
                "call_id": call_id,
                "company_id": company_id,
                "expires_at": exp_timestamp
            }

        except (ValueError, KeyError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid token format: {str(e)}"
            )

    @classmethod
    def generate_proxied_url(
            cls,
            call_id: UUID,
            company_id: UUID,
            base_url: str = "https://your-domain.com"
    ) -> str:
        """
        Generate a proxied URL for call recording

        Args:
            call_id: The call event ID
            company_id: The company ID
            base_url: Your application's base URL

        Returns:
            Proxied URL with signed token
        """
        token = cls.generate_token(call_id, company_id)
        return f"{base_url}/api/v1/company/recordings/proxy/{token}"
