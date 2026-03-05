from cachetools import TTLCache
from httpx import AsyncClient
from sqlalchemy.util import md5_hex

cache = TTLCache(maxsize=100, ttl=300)


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

    @classmethod
    async def get_operators(cls, *, user, secret):
        cache_key = f"{user}:{str(secret)}"

        if cache_key in cache:
            return cache[cache_key]

        async with AsyncClient() as client:
            payload = {
                "user": user,
                "hash": md5_hex("+".join([user, str(secret)]))

            }
            response = await client.get(cls.host + "/api/statistic/operators", params=payload, timeout=30)
            cache[cache_key] = response
            return response

    @classmethod
    async def get_operators_json(cls, *, user, secret) -> dict[str, dict[str, str]]:
        response = await cls.get_operators(user=user, secret=secret)
        if response.status_code != 200:
            response.raise_for_status()
        csv = map(lambda x: x.split(';'), response.content.decode('utf-8').split('\n')[1:])
        operators = {i[0]: {'name': i[1], 'status': i[2], 'call_state': i[3]} for i in csv if len(i) >= 4}
        return operators
