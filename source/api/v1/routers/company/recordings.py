"""
Call recording streaming endpoint
"""

import ipaddress
import os
import logging
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from utils.permissions import require_permissions, Permissions
from utils.services.telephony.http_client import get_http_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recordings", tags=["Recordings"])

# Configurable list of allowed recording provider hostnames
_allowed_hosts_raw = os.getenv("ALLOWED_RECORDING_HOSTS", "")
ALLOWED_RECORDING_HOSTS = [
    h.strip().lower()
    for h in _allowed_hosts_raw.split(",")
    if h.strip()
]

# Default provider hostnames when ALLOWED_RECORDING_HOSTS is unset
_DEFAULT_RECORDING_HOSTS = [
    "sipuni.com",
    "www.sipuni.com",
    "api.sipuni.com",
    "binotel.com",
    "www.binotel.com",
    "api.binotel.com",
    "my.binotel.ua",
]


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/loopback IP address."""
    try:
        addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except (socket.gaierror, ValueError):
        return True  # If we can't resolve, block it


def _validate_recording_url(url: str) -> None:
    """
    Validate that a recording URL is safe to fetch.

    Rules:
    - Must use https:// scheme
    - Hostname must be in the ALLOWED_RECORDING_HOSTS whitelist
      (defaults to known provider hostnames if unset)
    - Must not resolve to private/loopback IP ranges
    """
    parsed = urlparse(url)

    # Only allow https scheme
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recording URL must use HTTPS",
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recording URL has no valid hostname",
        )

    # Check against private/loopback IPs
    if _is_private_ip(hostname):
        logger.warning(
            f"Recording URL hostname '{hostname}' resolves to private/loopback IP"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recording host not allowed",
        )

    # Use configured whitelist, or fall back to known provider hosts
    allowed = ALLOWED_RECORDING_HOSTS or _DEFAULT_RECORDING_HOSTS
    if hostname not in allowed:
        logger.warning(
            f"Recording URL hostname '{hostname}' not in allowed hosts whitelist"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recording host not allowed",
        )


@router.get("/{call_id}")
@require_permissions(Permissions.CALLS_READ)
async def stream_recording(
    call_id: int,
    user: User = User.current(),
    session: AsyncSession = Depends(get_session),
):
    """
    Stream call recording by call ID.

    Requires JWT authentication and CALLS_READ permission.
    The provider URL is never exposed to the client.

    Security:
    - Only HTTPS recording URLs are allowed
    - Hostname must be in ALLOWED_RECORDING_HOSTS whitelist (if configured)
    - HTTP redirects are blocked
    """
    call = await CallEvent.get(
        session=session,
        id=call_id,
        company_id=user.company_id,
    )
    if not call or not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found",
        )

    # Validate the recording URL before fetching
    _validate_recording_url(call.record_url)

    http_client = await get_http_client()

    # Allow redirects — Sipuni may redirect to CDN for the actual file
    response = await http_client.get(
        call.record_url,
        timeout=300,
        allow_redirects=True,
    )

    if response.status != 200:
        response.release()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording file not accessible",
        )

    async def stream_chunks():
        try:
            async for chunk in response.content.iter_chunked(64 * 1024):
                yield chunk
        finally:
            response.release()

    headers = {
        "Content-Disposition": f'inline; filename="recording_{call.id}.mp3"',
    }
    content_length = response.headers.get("Content-Length")
    if content_length:
        headers["Content-Length"] = content_length

    return StreamingResponse(
        stream_chunks(),
        media_type=response.headers.get("Content-Type", "audio/mpeg"),
        headers=headers,
    )
