from fastapi import APIRouter

router = APIRouter(prefix='/sipuni', tags=['SIPUNI'])

from . import stream, create, read, update, delete, call

__all__ = ["router"]
