import asyncio

from httpx import AsyncClient
from sqlalchemy.util import md5_hex


async def external_call(*, user, secret, phone_from, phone_to, sip_number, sip_number2):
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


if __name__ == "__main__":
    a = external_call(
        user="097380",
        secret="0.ta3k9y7tki",
        phone_from="998200083233",
        phone_to="998999151330",
        sip_number="201",
        sip_number2="201",
    )
    asyncio.run(a)
