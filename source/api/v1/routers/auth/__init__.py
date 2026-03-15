from fastapi import APIRouter

router = APIRouter(prefix='/auth', tags=['Auth'])

from . import auth
from . import telegram_auth
from . import telegram_miniapp

__all__ = ['router']
