"""
Call recording streaming endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from db.models.user import User
from db.models.call_event import CallEvent
from utils.permissions import require_permissions, Permissions
from utils.services.telephony.http_client import get_http_client

router = APIRouter(prefix="/recordings", tags=["Recordings"])


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

    http_client = await get_http_client()
    response = await http_client.get(call.record_url, timeout=300)

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
        "Content-Disposition": f'attachment; filename="recording_{call.id}.mp3"',
    }
    content_length = response.headers.get("Content-Length")
    if content_length:
        headers["Content-Length"] = content_length

    return StreamingResponse(
        stream_chunks(),
        media_type=response.headers.get("Content-Type", "audio/mpeg"),
        headers=headers,
    )
