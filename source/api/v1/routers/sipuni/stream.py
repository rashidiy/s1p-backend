from pydantic import TypeAdapter
from starlette.requests import Request

from api.v1.schemas import SipuniEvent
from . import router


@router.get('/stream', tags=['Streams'])
async def stream(request: Request):
    try:
        event_model = TypeAdapter(SipuniEvent).validate_python(request.query_params)
        print(event_model.model_dump())
    except Exception as e:
        print(e)
    return {"success": True}
