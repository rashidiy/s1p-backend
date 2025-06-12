from . import router


@router.get('/external_call')
async def external_call():
    return {}
