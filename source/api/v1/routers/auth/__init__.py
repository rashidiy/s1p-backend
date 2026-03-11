from fastapi import APIRouter

router = APIRouter(prefix='/auth', tags=['Auth'])

from . import auth
from . import telegram_auth

__all__ = ['router']
