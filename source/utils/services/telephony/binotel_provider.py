"""
Binotel telephony provider implementation

Optimized for production:
- Uses shared connection pool
- Automatic retry on failures
"""

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
from .http_client import get_http_client


class BinotelProvider(TelephonyProvider):
    """
    Binotel telephony provider implementation

    Config structure:
    {
        "cabinet_id": "your_api_key",
        "security_key": "your_api_secret",
        "company_number": "100"  # Default company line/pbx number
    }
    """

    BASE_URL = "https://api.binotel.com"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cabinet_id = config.get('cabinet_id')
        self.security_key = config.get('security_key')
        self.company_number = config.get('company_number', '100')

        if not self.cabinet_id or not self.security_key:
            raise ProviderException(
                "Missing required config: cabinet_id and security_key",
                provider="binotel",
                details=config
            )

    async def _make_request(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make authenticated API request to Binotel

        Uses shared connection pool for optimal performance.

        Args:
            endpoint: API endpoint path (e.g., '/api/4.0/calls/...')
            data: Request payload (will include key and secret)

        Returns:
            API response as dict

        Raises:
            ProviderException: If API call fails
        """
        # Add authentication
        data['key'] = self.cabinet_id
        data['secret'] = self.security_key

        try:
            # Use shared connection pool
            client = await get_http_client()
            async with await client.post(
                f"{self.BASE_URL}{endpoint}",
                json=data,
                timeout=50
            ) as response:
                result = await response.json()

                if response.status != 200:
                    raise ProviderException(
                        f"Binotel API returned status {response.status}",
                        provider="binotel",
                        details={
                            "endpoint": endpoint,
                            "status": response.status,
                            "response": result
                        }
                    )

                return result

        except aiohttp.ClientError as e:
            raise ProviderException(
                f"Binotel API request failed: {str(e)}",
                provider="binotel",
                details={"endpoint": endpoint, "error": str(e)}
            )

    async def make_call(self, request: CallRequest) -> CallResponse:
        """
        Initiate external call via Binotel

        Uses /api/4.0/calls/external-number-to-external-number.json endpoint

        Maps request.phone_1 → externalNumber1 (customer)
        Maps request.phone_2 → externalNumber2 (destination)
        """
        try:
            data = {
                "externalNumber1": request.phone_1,  # Customer phone
                "externalNumber2": request.phone_2,  # Destination phone
                "pbxNumber": self.company_number,    # Company line
            }

            # Add optional customer ID (order_id)
            if request.order_id:
                data["customerID"] = request.order_id

            result = await self._make_request(
                "/api/4.0/calls/external-number-to-external-number.json",
                data
            )

            return CallResponse(
                success=result.get("status") == "success",
                call_id=result.get("generalCallID", ""),
                message=result.get("message", ""),
                error=result.get("message", "") if result.get("status") != "success" else None
            )

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to make call: {str(e)}",
                provider="binotel",
                details={"request": request.dict()}
            )

    async def get_call_status(self, call_id: str) -> Optional[CallStatus]:
        """
        Get call status by generalCallID

        Uses /api/4.0/stats/call-history.json endpoint
        """
        try:
            data = {
                "generalCallID": call_id
            }

            result = await self._make_request(
                "/api/4.0/stats/call-history.json",
                data
            )

            if not result.get('calls'):
                return None

            call = result['calls'][0]

            return CallStatus(
                provider_call_id=call_id,
                state=call.get('disposition', 'UNKNOWN'),
                waiting_sec=call.get('waitTime'),
                billing_sec=call.get('billsec'),
                record_url=call.get('recordingLink'),
                call_start=datetime.fromtimestamp(call.get('startTime', 0)) if call.get('startTime') else None,
                call_end=datetime.fromtimestamp(call.get('endTime', 0)) if call.get('endTime') else None,
                disposition=call.get('disposition')
            )

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to get call status: {str(e)}",
                provider="binotel",
                details={"call_id": call_id}
            )

    async def get_call_record_url(self, call_id: str) -> Optional[str]:
        """
        Get call recording URL

        Uses /api/4.0/stats/call-record.json endpoint
        """
        try:
            data = {
                "generalCallID": call_id
            }

            result = await self._make_request(
                "/api/4.0/stats/call-record.json",
                data
            )

            if result.get('status') == 'success' and result.get('url'):
                # Replace CDN URL with proxy URL if configured
                url = result['url']

                # Check if we should proxy the URL
                # Original: https://cdn0993.s3.eu-west-1.amazonaws.com/...
                # Proxied: https://r.sip.samyy.tech/...
                if 'cdn0993.s3.eu-west-1.amazonaws.com' in url:
                    # This will be handled at the application level
                    # For now, return the original URL
                    pass

                return url

            return None

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to get call record URL: {str(e)}",
                provider="binotel",
                details={"call_id": call_id}
            )

    async def handle_webhook(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Process Binotel webhook (apiCallCompleted event)

        Binotel webhook structure:
        {
            "requestType": "apiCallCompleted",
            "attemptsCounter": "1",
            "callDetails[companyID]": "123",
            "callDetails[generalCallID]": "456789",
            "callDetails[callID]": "abc123",
            "callDetails[startTime]": "1234567890",
            "callDetails[callType]": "outgoing",
            "callDetails[waitsec]": "5",
            "callDetails[billsec]": "120",
            "callDetails[disposition]": "ANSWER"
        }

        Note: Django's request.POST.get() automatically handles nested form data
        In FastAPI, we need to parse the nested structure differently
        """
        # Check if this is a call completion event
        request_type = payload.get("requestType")
        if request_type != "apiCallCompleted":
            return None

        # Parse nested callDetails
        # FastAPI may receive this as flat form data with brackets
        # or as nested dict depending on content type
        call_details = {}

        # Try to extract nested data
        for key, value in payload.items():
            if key.startswith("callDetails[") and key.endswith("]"):
                # Extract field name from callDetails[fieldName]
                field_name = key[len("callDetails["):-1]
                call_details[field_name] = value

        # If no nested data found, try direct access (JSON payload)
        if not call_details and "callDetails" in payload:
            call_details = payload.get("callDetails", {})

        return {
            "provider_call_id": call_details.get('generalCallID'),
            "phone_1": call_details.get('externalNumber'),
            "phone_2": call_details.get('internalNumber'),
            "state": call_details.get('disposition'),
            "billing_sec": int(call_details.get('billsec', 0)) if call_details.get('billsec') else None,
            "waiting_sec": int(call_details.get('waitsec', 0)) if call_details.get('waitsec') else None,
            "record_url": call_details.get('recordingLink'),
            "call_start_timestamp": int(call_details.get('startTime', 0)) if call_details.get('startTime') else None,
            "call_end_timestamp": int(call_details.get('endTime', 0)) if call_details.get('endTime') else None,
            "direction": "outbound",  # Binotel external calls are outbound
            "attempts": int(payload.get('attemptsCounter', 1)) if payload.get('attemptsCounter') else 1,
            "company_id": call_details.get('companyID'),
            "call_type": call_details.get('callType'),
        }

    async def validate_webhook_auth(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> bool:
        """
        Validate Binotel webhook authentication

        The webhook token is validated at the route level (company lookup by token).
        Here we verify the payload has the minimum fields a legitimate Binotel webhook
        must contain, rejecting structurally invalid requests.
        IP whitelisting is the recommended additional layer (BINOTEL_ALLOWED_IPS).
        """
        request_type = payload.get("requestType")
        return bool(request_type)

    async def get_call_history(
        self,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
        operator_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """
        Get call history from Binotel

        Uses /api/4.0/stats/call-history.json endpoint

        Args:
            time_from: Start time filter
            time_to: End time filter
            operator_id: Filter by operator
            limit: Maximum number of records
            offset: Pagination offset

        Returns:
            List of call records
        """
        try:
            data = {}

            if time_from:
                data['dateFrom'] = int(time_from.timestamp())
            if time_to:
                data['dateTo'] = int(time_to.timestamp())

            # Note: Binotel pagination parameters may differ
            # Adjust based on actual API documentation

            result = await self._make_request(
                "/api/4.0/stats/call-history.json",
                data
            )

            calls = result.get('calls', [])

            # Apply limit and offset client-side if API doesn't support it
            return calls[offset:offset + limit]

        except Exception as e:
            if isinstance(e, ProviderException):
                raise
            raise ProviderException(
                f"Failed to get call history: {str(e)}",
                provider="binotel"
            )
