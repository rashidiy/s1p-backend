"""
Call management endpoints

Structure:
    /calls/              — provider-agnostic (list, get, recording)
    /calls/sipuni/       — Sipuni-specific call actions
    /calls/binotel/      — Binotel-specific call actions
"""

from fastapi import APIRouter

from . import common, sipuni, binotel

router = APIRouter()

router.include_router(common.router)
router.include_router(sipuni.router)
router.include_router(binotel.router)

__all__ = ["router"]
