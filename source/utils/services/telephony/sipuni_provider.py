"""
Sipuni telephony provider implementation

Optimized for production:
- Uses shared connection pool
- Automatic retry on failures
"""

import hashlib
from typing import Dict, Any, Optional

import aiohttp

from .base import (
    TelephonyProvider,
    CallRequest,
    CallResponse,
    CallStatus,
    ProviderException
)
from .http_client import get_http_client


class SipuniProvider(TelephonyProvider):
    """
    Sipuni telephony provider implementation

    Config structure:
    {
        "cabinet_id": "12345",
        "security_key": "secret_key",
        "token": "webhook_token"  # For webhook validation
    }
    """

    BASE_URL = "https://sipuni.com"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cabinet_id = config.get('cabinet_id')
        self.security_key = config.get('security_key')
        self.webhook_token = config.get('token')

        if not self.cabinet_id or not self.security_key:
            raise ProviderException(
                "Missing required config: cabinet_id and security_key",
                provider="sipuni",
                details=config
            )

    def _generate_hash(self, *params: str) -> str:
        """
        Generate MD5 hash for Sipuni API authentication

        Params are joined with '+' and the security key is appended.
        The resulting string is MD5-hashed.
        """
        hash_string = "+".join(str(p) for p in params) + "+" + self.security_key
        return hashlib.md5(hash_string.encode()).hexdigest()

    async def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make authenticated POST request to Sipuni API

        Sipuni requires POST with form-encoded data.
        The 'user' param is set automatically from config.
        """
        params['user'] = self.cabinet_id

        try:
            client = await get_http_client()
            async with await client.post(
                f"{self.BASE_URL}{endpoint}",
                data=params,
                timeout=50
            ) as response:
                result = await response.json()

                if response.status != 200:
                    raise ProviderException(
                        f"Sipuni API returned status {response.status}",
                        provider="sipuni",
                        details={"endpoint": endpoint, "status": response.status, "response": result}
                    )

                return result

        except aiohttp.ClientError as e:
            raise ProviderException(
                f"Sipuni API request failed: {str(e)}",
                provider="sipuni",
                details={"endpoint": endpoint, "error": str(e)}
            )

    async def make_call(self, request: CallRequest) -> CallResponse:
        """
        Call from external number to another external number via Sipuni.

        Uses /api/callback/call_external endpoint.

        Hash order: phoneFrom + phoneTo + sipnumber + sipnumber2 + user + secret
        """
        if not request.operator_id:
            raise ProviderException(
                "operator_id (SIP number) is required for Sipuni calls",
                provider="sipuni"
            )

        sipnumber = request.operator_id

        params = {
            "phoneFrom": request.phone_1,
            "phoneTo": request.phone_2,
            "sipnumber": sipnumber,
            "sipnumber2": sipnumber,
            "hash": self._generate_hash(
                request.phone_1, request.phone_2,
                sipnumber, sipnumber,
                self.cabinet_id
            ),
        }

        result = await self._make_request("/api/callback/call_external", params)

        return CallResponse(
            success=result.get("result") is True,
            call_id=result.get("callID", ""),
            message=result.get("message", "")
        )

    async def call_number(
        self,
        phone: str,
        sipnumber: str,
        reverse: bool = False,
        antiaon: bool = False,
    ) -> CallResponse:
        """
        Call from internal SIP number to external phone number.

        Uses /api/callback/call_number endpoint.

        Hash order: antiaon + phone + reverse + sipnumber + user + secret
        """
        reverse_str = str(int(reverse))
        antiaon_str = str(int(antiaon))

        params = {
            "phone": phone,
            "sipnumber": sipnumber,
            "reverse": reverse_str,
            "antiaon": antiaon_str,
            "hash": self._generate_hash(
                antiaon_str, phone, reverse_str, sipnumber, self.cabinet_id
            ),
        }

        result = await self._make_request("/api/callback/call_number", params)

        return CallResponse(
            success=result.get("result") is True,
            call_id=result.get("callID", ""),
            message=result.get("message", "")
        )

    async def call_tree(
        self,
        phone: str,
        sipnumber: str,
        tree: str,
        reverse: bool = False,
        call_attempt_time: int = 30,
    ) -> CallResponse:
        """
        Call external number through a call tree/scheme (IVR).

        Uses /api/callback/call_tree endpoint.

        Hash order: callAttemptTime + phone + reverse + sipnumber + tree + user + secret
        """
        reverse_str = str(int(reverse))
        attempt_str = str(call_attempt_time)

        params = {
            "phone": phone,
            "sipnumber": sipnumber,
            "tree": tree,
            "reverse": reverse_str,
            "callAttemptTime": attempt_str,
            "hash": self._generate_hash(
                attempt_str, phone, reverse_str, sipnumber, tree, self.cabinet_id
            ),
        }

        result = await self._make_request("/api/callback/call_tree", params)

        return CallResponse(
            success=result.get("result") is True,
            call_id=result.get("callID", ""),
            message=result.get("message", "")
        )

    async def cancel_call(self, call_id: str) -> CallResponse:
        """
        Cancel an active callback call.

        Uses /api/callback/cancel endpoint.

        Hash order: callbackId + user + secret
        """
        params = {
            "callbackId": call_id,
            "hash": self._generate_hash(call_id, self.cabinet_id),
        }

        result = await self._make_request("/api/callback/cancel", params)

        return CallResponse(
            success=result.get("result") is True,
            call_id=call_id,
            message=result.get("message", "")
        )

    async def get_call_status(self, call_id: str) -> Optional[CallStatus]:
        """
        Get call status by call_id

        Note: Sipuni primarily uses webhooks for status updates.
        """
        return None

    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """
        Get call recording URL

        Sipuni provides record URLs via webhooks (stream events).
        """
        return None

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Sipuni webhook (stream event)

        Returns normalized call data or None if not a hangup event (event=2).
        """
        if payload.get('event') != 2:
            return None

        return {
            "provider_call_id": payload.get('call_id'),
            "phone_1": payload.get('src_num'),
            "phone_2": payload.get('pbxdstnum'),
            "state": payload.get('status'),
            "call_start_timestamp": payload.get('call_start_timestamp'),
            "call_end_timestamp": payload.get('call_end_timestamp'),
            "record_url": payload.get('record_link'),
            "direction": self._determine_direction(payload),
            "last_called": payload.get('last_called', []),
            "dst_type": payload.get('dst_type'),
            "src_type": payload.get('src_type'),
            "transfer_from": payload.get('transfer_from'),
            "tree_number": payload.get('tree_number'),
        }

    def _determine_direction(self, payload: Dict[str, Any]) -> str:
        """Determine call direction from src_type/dst_type (1=external, 2=internal)"""
        src_type = payload.get('src_type', '1')
        dst_type = payload.get('dst_type', '2')

        if src_type == '1' and dst_type == '2':
            return 'inbound'
        elif src_type == '2' and dst_type == '1':
            return 'outbound'
        else:
            return 'internal'

    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate Sipuni webhook authentication

        Token validation happens at route level.
        """
        return True
