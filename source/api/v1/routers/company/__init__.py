"""
Company-level API endpoints (current company from JWT)

All endpoints under /company operate on the user's company from their JWT token.
"""

from fastapi import APIRouter

from . import calls, calls_enhanced, webhooks, recordings, users, analytics, contacts, leads, deals, tasks, notes, contract, permission_groups, custom_fields

router = APIRouter(prefix="/company", tags=["Company Operations"])

# Include sub-routers
router.include_router(calls.router)
router.include_router(calls_enhanced.router)  # Enhanced call management
router.include_router(webhooks.router)
router.include_router(recordings.router)
router.include_router(users.router)
router.include_router(analytics.router)

router.include_router(contract.router)

router.include_router(permission_groups.router)

# CRM modules
router.include_router(contacts.router)
router.include_router(leads.router)
router.include_router(deals.router)
router.include_router(tasks.router)
router.include_router(notes.router)
router.include_router(custom_fields.router)

__all__ = ["router"]
