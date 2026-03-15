"""
Dual-auth recording endpoint — signed URL (24h) or JWT cookie fallback.

Used by Telegram notifications: signed URL lets anyone play the recording
for 24 hours. After that, only logged-in CRM users (JWT cookie) can access it.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.call_event import CallEvent
from utils.services.signed_url_service import verify_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recordings", tags=["Recordings (Public)"])


async def _try_jwt_auth(request: Request) -> Optional[tuple]:
    """Try to authenticate via JWT cookie. Returns (user_id, company_id) or None."""
    try:
        from utils.auth import get_current_user_from_cookie
        user = await get_current_user_from_cookie(request)
        if user:
            return user.id, user.company_id
    except Exception:
        pass
    return None


@router.get("/{call_id}")
async def stream_recording_dual_auth(
    call_id: int,
    request: Request,
    cid: Optional[str] = Query(None, description="Company ID (signed URL)"),
    exp: Optional[str] = Query(None, description="Expiry timestamp (signed URL)"),
    sig: Optional[str] = Query(None, description="HMAC signature (signed URL)"),
    session: AsyncSession = Depends(get_session),
):
    """
    Stream call recording with dual authentication.

    Auth method 1: Signed URL params (?cid=...&exp=...&sig=...)
    Auth method 2: JWT cookie (existing auth for logged-in CRM users)

    Tries signed URL first → if expired/invalid, falls back to JWT → if neither, 403.
    """
    company_id = None

    # Method 1: Signed URL
    if cid and exp and sig:
        is_valid, error = verify_signature(
            call_id=str(call_id),
            company_id=cid,
            exp=exp,
            sig=sig,
        )
        if is_valid:
            company_id = cid
        else:
            logger.debug("Signed URL invalid for call %s: %s", call_id, error)

    # Method 2: JWT cookie fallback
    if not company_id:
        jwt_result = await _try_jwt_auth(request)
        if jwt_result:
            _, company_id_uuid = jwt_result
            company_id = str(company_id_uuid)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required — signed URL expired or no active session",
        )

    # Fetch call event with company isolation
    from sqlalchemy import select
    result = await session.execute(
        select(CallEvent).where(
            CallEvent.id == call_id,
            CallEvent.company_id == company_id,
        )
    )
    call = result.scalar_one_or_none()

    if not call or not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found",
        )

    # Stream from provider
    from utils.services.telephony.http_client import get_http_client
    from api.v1.routers.company.recordings import _validate_recording_url

    _validate_recording_url(call.record_url)

    http_client = await get_http_client()
    response = await http_client.get(
        call.record_url,
        timeout=300,
        allow_redirects=False,
    )

    if 300 <= response.status < 400:
        response.release()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Recording redirect blocked")

    if response.status != 200:
        response.release()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording file not accessible")

    async def stream_chunks():
        try:
            async for chunk in response.content.iter_chunked(64 * 1024):
                yield chunk
        finally:
            response.release()

    headers = {"Content-Disposition": f'inline; filename="recording_{call.id}.mp3"'}
    content_length = response.headers.get("Content-Length")
    if content_length:
        headers["Content-Length"] = content_length

    return StreamingResponse(
        stream_chunks(),
        media_type=response.headers.get("Content-Type", "audio/mpeg"),
        headers=headers,
    )
