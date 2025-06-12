from fastapi import APIRouter

router = APIRouter()

from . import stream

__all__ = ["router"]
