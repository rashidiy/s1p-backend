from fastapi import APIRouter

router = APIRouter(prefix='/auth', tags=['Auth'])

from . import auth, verification

__all__ = ['router']
