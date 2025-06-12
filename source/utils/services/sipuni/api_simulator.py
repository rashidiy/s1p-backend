from httpx import AsyncClient
from sqlalchemy.util import md5_hex


class SipuniApiSimulator:
    @classmethod
    async def external_call(cls, *, user, secret, phone_from, phone_to, sip_number, sip_number2):
        async with AsyncClient() as client:
            payload = {
                "user": user,
                "phoneFrom": phone_from,
                "phoneTo": phone_to,
                "sipnumber": sip_number,
                "sipnumber2": sip_number2,
                "hash": md5_hex("+".join([phone_from, phone_to, sip_number, sip_number2, user, secret]))
            }
            response = await client.get("https://sipuni.com/api/callback/call_external", params=payload, timeout=50)
            print(response.json())
