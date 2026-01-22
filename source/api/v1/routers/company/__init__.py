"""
Company-level API endpoints (current company from JWT)

All endpoints under /company operate on the user's company from their JWT token.
"""

from fastapi import APIRouter

from . import calls, webhooks, recordings

router = APIRouter(prefix="/company", tags=["Company Operations"])

# Include sub-routers
router.include_router(calls.router)
router.include_router(webhooks.router)
router.include_router(recordings.router)

__all__ = ["router"]
