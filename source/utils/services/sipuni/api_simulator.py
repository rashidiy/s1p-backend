from httpx import AsyncClient
from sqlalchemy.util import md5_hex


class SipuniApiSimulator:
    host = 'https://sipuni.com'

    @classmethod
    async def external_call(cls, *, user, secret, phone_from, phone_to, sipnumber, sipnumber2):
        async with AsyncClient() as client:
            payload = {
                "user": user,
                "phoneFrom": phone_from,
                "phoneTo": phone_to,
                "sipnumber": sipnumber,
                "sipnumber2": sipnumber2,
                "hash": md5_hex("+".join([phone_from, phone_to, sipnumber, sipnumber2, user, secret]))
            }
            return await client.get(cls.host + "/api/callback/call_external", params=payload, timeout=50)

    @classmethod
    async def call_number(cls, *, user, secret, phone, sipnumber, reverse: int = False, antiaon: bool = False):
        reverse, antiaon = str(int(reverse)), str(int(antiaon))

        async with AsyncClient() as client:
            payload = {
                "user": user,
                "phone": phone,
                "sipnumber": sipnumber,
                "reverse": reverse,
                "antiaon": antiaon,
                "hash": md5_hex("+".join([antiaon, phone, reverse, sipnumber, user, secret]))
            }

            return await client.get(cls.host + "/api/callback/call_number", params=payload, timeout=50)

    @classmethod
    async def call_tree(cls, *, user, secret, phone, sipnumber, tree, reverse: bool = False,
                        attempt_duration: int = 30):
        reverse = str(int(reverse))

        async with AsyncClient() as client:
            payload = {
                "user": user,
                "phone": phone,
                "sipnumber": sipnumber,
                "tree": tree,
                "reverse": reverse,
                "callAttemptTime": attempt_duration,
                "hash": md5_hex("+".join([str(attempt_duration), phone, reverse, sipnumber, tree, user, secret]))
            }
            return await client.get(cls.host + "/api/callback/call_tree", params=payload, timeout=attempt_duration + 30)
