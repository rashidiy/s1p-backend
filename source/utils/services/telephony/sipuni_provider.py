"""
Sipuni telephony provider implementation

Optimized for production:
- Uses shared connection pool
- Automatic retry on failures
- Handles all 4 webhook events (call start, hang-up, answer, transfer)
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

    def _parse_result(self, data: Dict[str, Any]) -> CallResponse:
        """Build a CallResponse from a Sipuni JSON body.

        Sipuni returns: {"success": True, "id": "<hash>"}
        """
        success = bool(data.get("success"))
        call_id = str(data.get("id") or "")
        message = data.get("message") or data.get("msg") or ""
        error = None if success else (message or "Unknown error")

        return CallResponse(
            success=success,
            call_id=call_id,
            message=message,
            error=error,
        )

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
                # content_type=None: Sipuni may respond with text/html
                result = await response.json(content_type=None)
                if response.status != 200:
                    raise ProviderException(
                        f"Sipuni API returned status {response.status}",
                        provider="sipuni",
                        details={"endpoint": endpoint, "status": response.status, "response": result}
                    )

                return result

        except ProviderException:
            raise
        except Exception as e:
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
        return self._parse_result(result)

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
        return self._parse_result(result)

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
        return self._parse_result(result)

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
        resp = self._parse_result(result)
        resp.call_id = resp.call_id or call_id
        return resp

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

    # ── Webhook handling ──────────────────────────────────────

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Sipuni webhook events.

        Handles all 4 event types:
          1 = Call start (RINGING)
          2 = Hang-up (final state)
          3 = Answer (call_answer_timestamp)
          4 = Transfer hang-up (transfer info + partial end)

        Returns normalized call data dict with '_event_type' key for handler logic.
        Returns None for unknown event types.
        """
        event = str(payload.get('event', ''))

        if event == '1':
            return self._handle_call_start(payload)
        elif event == '2':
            return self._handle_hangup(payload)
        elif event == '3':
            return self._handle_answer(payload)
        elif event == '4':
            return self._handle_transfer_hangup(payload)

        return None

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number to +998 format.

        Handles:
        - Sipuni _id suffix (998783337125_id265648 → +998783337125)
        - 9-digit local numbers (990002170 → +998990002170)
        - 12-digit numbers with 998 prefix (998990002170 → +998990002170)
        """
        if not phone:
            return phone

        # Strip Sipuni _id suffix (e.g. _id265648)
        if '_id' in phone:
            phone = phone.split('_id')[0]

        # Strip leading + if present
        phone = phone.lstrip('+')

        # 9 digits — local Uzbek number, prepend 998
        if len(phone) == 9 and phone[0] in '0123456789':
            phone = '998' + phone

        # Add + prefix if it looks like a full number (12 digits starting with 998)
        if len(phone) >= 10:
            phone = '+' + phone

        return phone

    def _extract_common_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields common to all webhook events."""
        provider_id = payload.get('callbackId') or payload.get('call_id', '')

        src_num = payload.get('src_num', '')
        if self.cabinet_id and src_num.startswith(str(self.cabinet_id)):
            src_num = src_num[len(str(self.cabinet_id)):]

        # Prefer pbxdstnum (clean) over dst_num (may have _id suffix)
        dst_num = payload.get('pbxdstnum') or payload.get('dst_num', '')

        return {
            "provider_call_id": f"sipuni_{provider_id}",
            "phone_1": self._normalize_phone(src_num),
            "phone_2": self._normalize_phone(dst_num),
            "direction": self._determine_direction(payload),
            "scheme_name": payload.get('treeName') or None,
            "scheme_number": payload.get('treeNumber') or None,
        }

    def _handle_call_start(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Event 1: Call initiated — create record with RINGING state."""
        data = self._extract_common_fields(payload)
        timestamp = payload.get('timestamp')

        data.update({
            "state": "RINGING",
            "call_start_timestamp": int(timestamp) if timestamp else None,
            "last_called": payload.get('last_called') or None,
            "_event_type": "call_started",
        })
        return data

    def _handle_hangup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Event 2: Call ended — set final state, recording, timestamps."""
        data = self._extract_common_fields(payload)

        call_start = payload.get('call_start_timestamp')
        call_end = payload.get('timestamp')
        call_answer = payload.get('call_answer_timestamp')

        data.update({
            "state": payload.get('status'),
            "call_start_timestamp": int(call_start) if call_start else None,
            "call_end_timestamp": int(call_end) if call_end else None,
            "call_answer_timestamp": int(call_answer) if call_answer and str(call_answer) != '0' else None,
            "record_url": payload.get('call_record_link') or None,
            "transfer_from": payload.get('transfer_from') or None,
            "last_called": payload.get('last_called') or None,
            "_event_type": "call_ended",
        })
        return data

    def _handle_answer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Event 3: Call answered — record answer timestamp."""
        data = self._extract_common_fields(payload)
        timestamp = payload.get('timestamp')

        data.update({
            "call_answer_timestamp": int(timestamp) if timestamp else None,
            "last_called": payload.get('last_called') or None,
            "_event_type": "call_answered",
        })
        # Don't set state — let event 2 set the final state
        return data

    def _handle_transfer_hangup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Event 4: Transfer hang-up — mark as transfer, record transfer info."""
        data = self._extract_common_fields(payload)

        call_start = payload.get('call_start_timestamp')
        call_end = payload.get('timestamp')
        call_answer = payload.get('call_answer_timestamp')

        data.update({
            "state": payload.get('status'),
            "call_start_timestamp": int(call_start) if call_start else None,
            "call_end_timestamp": int(call_end) if call_end else None,
            "call_answer_timestamp": int(call_answer) if call_answer and str(call_answer) != '0' else None,
            "record_url": payload.get('call_record_link') or None,
            "is_transfer": True,
            "transfer_from": payload.get('transfer_from') or None,
            "last_called": payload.get('last_called') or None,
            "_event_type": "call_transferred",
        })
        return data

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

        The webhook token is validated at the route level (company lookup by token).
        Here we verify the payload has the minimum fields a legitimate Sipuni webhook
        must contain, rejecting structurally invalid requests.
        """
        return bool(payload.get("event") and payload.get("call_id"))
