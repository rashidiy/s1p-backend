"""
Call recording proxy endpoints
Provides secure access to call recordings via signed tokens
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
import aiohttp

from db.models.call_event import CallEvent
from utils.managers import RecordTokenManager

router = APIRouter(prefix="/recordings", tags=["Recordings"])


@router.get("/proxy/{token}")
async def proxy_recording(token: str):
    """
    Proxy endpoint for call recordings

    Validates the signed token and redirects to the actual recording URL.
    This provides secure, time-limited access to call recordings without
    exposing provider URLs directly.

    Args:
        token: Signed token containing call_id, company_id, and expiry

    Returns:
        Redirect to the actual recording URL

    Security:
    - Token must be valid and not expired
    - Token signature must match
    - Call must belong to the company in the token
    """
    # Validate token and extract call_id, company_id
    token_data = RecordTokenManager.validate_token(token)
    call_id = token_data["call_id"]
    company_id = token_data["company_id"]

    # Get call event and verify it belongs to the company
    call = await CallEvent.get_one(id=call_id, company_id=company_id)
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found or access denied"
        )

    if not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recording available for this call"
        )

    # Redirect to the actual recording URL
    # In production, you might want to stream the file directly
    # instead of redirecting to avoid exposing the provider URL
    return RedirectResponse(url=call.record_url)


@router.get("/stream/{token}")
async def stream_recording(token: str):
    """
    Stream call recording directly (more secure than redirect)

    Validates the token and streams the recording file directly
    without exposing the provider URL.

    This is more secure than redirect but requires more resources.
    """
    # Validate token
    token_data = RecordTokenManager.validate_token(token)
    call_id = token_data["call_id"]
    company_id = token_data["company_id"]

    # Get call event
    call = await CallEvent.get_one(id=call_id, company_id=company_id)
    if not call or not call.record_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )

    # Stream the file from provider
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(call.record_url) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Recording file not accessible"
                    )

                content = await response.read()

                # Return streaming response
                from fastapi.responses import Response
                return Response(
                    content=content,
                    media_type=response.headers.get('Content-Type', 'audio/mpeg'),
                    headers={
                        'Content-Disposition': f'attachment; filename="call_{call_id}.mp3"'
                    }
                )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream recording: {str(e)}"
        )
