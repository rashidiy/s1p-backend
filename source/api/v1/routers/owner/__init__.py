"""
Owner-level API endpoints

Owners are platform administrators who can create and manage multiple companies.
"""

from fastapi import APIRouter

from . import auth, companies, contracts, analytics

router = APIRouter(prefix="/owner", tags=["Owner Operations"])

# Include sub-routers
router.include_router(auth.router)
router.include_router(companies.router)
router.include_router(contracts.router)
router.include_router(analytics.router)

__all__ = ["router"]
