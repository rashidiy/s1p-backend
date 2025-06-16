from db.models import User
from . import router


@router.get('/send_verification')
async def send_verification_code(user: User = User.current(check_for_active=False)):
    ...


@router.get('/confirm_verification')
async def send_verification_code(user: User = User.current(check_for_active=False)):
    ...
