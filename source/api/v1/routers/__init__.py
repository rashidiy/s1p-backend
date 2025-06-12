from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")

from .sipuni import router as sipuni_router

for r in [sipuni_router]:
    router.include_router(r)

__all__ = ["router"]
