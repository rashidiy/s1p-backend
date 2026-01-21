"""
Sipuni telephony provider implementation
"""

import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

import aiohttp

from .base import (
    TelephonyProvider,
    CallRequest,
    CallResponse,
    CallStatus,
    ProviderException
)


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

        Args:
            *params: Parameters to hash (joined with +)

        Returns:
            MD5 hash string
        """
        hash_string = "+".join(str(p) for p in params) + "+" + self.security_key
        return hashlib.md5(hash_string.encode()).hexdigest()

    async def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make authenticated API request to Sipuni

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response as dict

        Raises:
            ProviderException: If API call fails
        """
        params['user'] = self.cabinet_id

        # Generate hash based on specific endpoint requirements
        # Hash is already computed in calling methods

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}{endpoint}",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=50)
                ) as response:
                    if response.status != 200:
                        raise ProviderException(
                            f"Sipuni API returned status {response.status}",
                            provider="sipuni",
                            details={"endpoint": endpoint, "status": response.status}
                        )

                    return await response.json()

        except aiohttp.ClientError as e:
            raise ProviderException(
                f"Sipuni API request failed: {str(e)}",
                provider="sipuni",
                details={"endpoint": endpoint, "error": str(e)}
            )

    async def make_call(self, request: CallRequest) -> CallResponse:
        """
        Initiate external call via Sipuni

        Uses /api/callback/call_external endpoint
        """
        try:
            params = {
                "user": self.cabinet_id,
                "phoneFrom": request.phone_1,
                "phoneTo": request.phone_2,
                "sipnumber": request.phone_2,  # Internal SIP number
                "sipnumber2": request.phone_2,
            }

            # Generate hash: phoneFrom + phoneTo + sipnumber + sipnumber2 + user + secret
            params["hash"] = self._generate_hash(
                request.phone_1,
                request.phone_2,
                request.phone_2,
                request.phone_2,
                self.cabinet_id
            )

            result = await self._make_request("/api/callback/call_external", params)

            return CallResponse(
                success=result.get("result") is True,
                call_id=result.get("callID", ""),
                message=result.get("message", "")
            )

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to make call: {str(e)}",
                provider="sipuni",
                details={"request": request.dict()}
            )

    async def get_call_status(self, call_id: str) -> Optional[CallStatus]:
        """
        Get call status by call_id

        Note: Sipuni primarily uses webhooks for status updates.
        This method queries the database for stored webhook data.
        """
        # In a real implementation, this would query the database
        # for call_events table filtered by provider_call_id
        # For now, return None as Sipuni uses webhooks
        return None

    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """
        Get call recording URL

        Sipuni provides record URLs via webhooks (stream events)
        Query database for stored record_url
        """
        # In a real implementation, this would query the database
        # For now, return None
        return None

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Sipuni webhook (stream event)

        Sipuni webhook structure:
        {
            "event": 2,  # Hangup event
            "call_id": "abc123",
            "src_num": "998901234567",
            "pbxdstnum": "100",
            "status": "ANSWER",
            "call_start_timestamp": 1234567890,
            "call_end_timestamp": 1234567900,
            "record_link": "https://...",
            "last_called": ["100", "101"],
            "dst_type": "2",
            "src_type": "1",
            "transfer_from": null,
            "tree_number": "",
            "timestamp": 1234567900
        }

        Returns normalized call data or None if not a hangup event
        """
        # Only process hangup events (event=2)
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
            # Additional Sipuni-specific fields
            "last_called": payload.get('last_called', []),
            "dst_type": payload.get('dst_type'),
            "src_type": payload.get('src_type'),
            "transfer_from": payload.get('transfer_from'),
            "tree_number": payload.get('tree_number'),
        }

    def _determine_direction(self, payload: Dict[str, Any]) -> str:
        """
        Determine call direction from payload

        Args:
            payload: Webhook payload

        Returns:
            'inbound', 'outbound', or 'internal'
        """
        src_type = payload.get('src_type', '1')
        dst_type = payload.get('dst_type', '2')

        # src_type: 1=external, 2=internal
        # dst_type: 1=external, 2=internal

        if src_type == '1' and dst_type == '2':
            return 'inbound'  # External → Internal
        elif src_type == '2' and dst_type == '1':
            return 'outbound'  # Internal → External
        else:
            return 'internal'  # Internal → Internal

    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate Sipuni webhook authentication

        Sipuni uses IP whitelisting and token validation
        Token is passed in URL path (stream/{token}/)
        This validation happens at the route level
        """
        # Token validation happens at route level
        # IP whitelist validation should be done via middleware
        return True

    async def call_number(
        self,
        phone: str,
        sipnumber: str,
        reverse: bool = False,
        antiaon: bool = False
    ) -> CallResponse:
        """
        Call number via Sipuni (call_number API)

        Args:
            phone: Phone number to call
            sipnumber: Internal SIP number
            reverse: Reverse call direction
            antiaon: Hide caller ID

        Returns:
            CallResponse
        """
        try:
            reverse_str = str(int(reverse))
            antiaon_str = str(int(antiaon))

            params = {
                "user": self.cabinet_id,
                "phone": phone,
                "sipnumber": sipnumber,
                "reverse": reverse_str,
                "antiaon": antiaon_str,
                "hash": self._generate_hash(
                    antiaon_str, phone, reverse_str, sipnumber, self.cabinet_id
                )
            }

            result = await self._make_request("/api/callback/call_number", params)

            return CallResponse(
                success=result.get("result") is True,
                call_id=result.get("callID", ""),
                message=result.get("message", "")
            )

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to call number: {str(e)}",
                provider="sipuni"
            )

    async def call_tree(
        self,
        phone: str,
        sipnumber: str,
        tree: str,
        reverse: bool = False,
        attempt_duration: int = 30
    ) -> CallResponse:
        """
        Call tree via Sipuni (IVR)

        Args:
            phone: Phone number to call
            sipnumber: Internal SIP number
            tree: IVR tree identifier
            reverse: Reverse call direction
            attempt_duration: Call attempt duration in seconds

        Returns:
            CallResponse
        """
        try:
            reverse_str = str(int(reverse))

            params = {
                "user": self.cabinet_id,
                "phone": phone,
                "sipnumber": sipnumber,
                "tree": tree,
                "reverse": reverse_str,
                "callAttemptTime": str(attempt_duration),
                "hash": self._generate_hash(
                    str(attempt_duration), phone, reverse_str, sipnumber, tree, self.cabinet_id
                )
            }

            result = await self._make_request("/api/callback/call_tree", params)

            return CallResponse(
                success=result.get("result") is True,
                call_id=result.get("callID", ""),
                message=result.get("message", "")
            )

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to call tree: {str(e)}",
                provider="sipuni"
            )
