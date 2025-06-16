from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

from .sipuni import router as sipuni_router
from .auth import router as auth_router

for r in [auth_router, sipuni_router]:
    router.include_router(r)

__all__ = ["router"]
