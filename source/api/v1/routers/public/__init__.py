"""
Public API endpoints — authenticated via X-API-Key header

Separate from internal JWT-authenticated API.
All endpoints are read-only and scoped by company_id from the API key.
"""

from fastapi import APIRouter

from . import contacts, leads, deals, calls

router = APIRouter(prefix="/api/public/v1", tags=["Public API"])

router.include_router(contacts.router)
router.include_router(leads.router)
router.include_router(deals.router)
router.include_router(calls.router)

__all__ = ["router"]
