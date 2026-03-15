"""
API v1 Router

Architecture:
- /auth - User authentication (company-level users)
- /owner - Owner operations (platform admins, create/manage companies)
- /company - Company operations (provider-agnostic, uses company's configured provider)

Legacy /sipuni endpoints have been removed. All telephony operations now use
the provider-agnostic /company endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

from .auth import router as auth_router
from .owner import router as owner_router
from .company import router as company_router
from .company.telegram_webhook import router as telegram_webhook_router
from .public.recordings import router as public_recordings_router

# Include routers in logical order
for r in [auth_router, owner_router, company_router, telegram_webhook_router, public_recordings_router]:
    router.include_router(r)

__all__ = ["router"]
