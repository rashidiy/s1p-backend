"""
Async Sipuni Dashboard API Client

Delegates all Sipuni dashboard interactions to a Cloudflare Worker
to avoid IP-based content restrictions from datacenter IPs.

The Worker handles: login, credential extraction, service activation,
and webhook configuration through Cloudflare's edge network.

Password is passed to the Worker over HTTPS and never stored.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

WORKER_URL = os.getenv(
    "SIPUNI_WORKER_URL",
    "https://s1p-cloudflare.bubbless7456.workers.dev",
)
WORKER_SECRET = os.getenv("SIPUNI_WORKER_SECRET", "")


class SipuniSetupError(Exception):
    """Base error for Sipuni setup operations."""


class LoginFailed(SipuniSetupError):
    """Authentication with Sipuni dashboard failed."""


class CredentialsNotFound(SipuniSetupError):
    """Could not extract API credentials from the dashboard."""


class WebhookSetupFailed(SipuniSetupError):
    """Failed to configure webhooks on Sipuni."""


class ServiceEnableFailed(SipuniSetupError):
    """Failed to enable a Sipuni integration service."""


ERROR_MAP = {
    "LoginFailed": LoginFailed,
    "CredentialsNotFound": CredentialsNotFound,
    "WebhookSetupFailed": WebhookSetupFailed,
    "ServiceEnableFailed": ServiceEnableFailed,
}


class SipuniAsyncClient:
    """Sipuni setup client that delegates to Cloudflare Worker.

    All Sipuni dashboard interactions go through the Worker to avoid
    IP-based restrictions on datacenter IPs.
    """

    async def _call_worker(self, action: str, **kwargs) -> dict:
        """Call the Cloudflare Worker with an action and parameters."""
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                WORKER_URL,
                json={"action": action, **kwargs},
                headers={"Authorization": f"Bearer {WORKER_SECRET}"},
            )

        data = resp.json()

        if resp.status_code != 200:
            error_type = data.get("error_type", "SipuniSetupError")
            error_msg = data.get("error", "Unknown error")
            exc_class = ERROR_MAP.get(error_type, SipuniSetupError)
            raise exc_class(error_msg)

        return data

    async def full_setup(self, email: str, password: str, webhook_url: str) -> dict:
        """Run the complete Sipuni setup flow via Cloudflare Worker.

        Returns dict with "user_id" and "secret_key" on success.
        """
        result = await self._call_worker(
            "full_setup",
            email=email,
            password=password,
            webhook_url=webhook_url,
        )

        return {
            "user_id": result["user_id"],
            "secret_key": result["secret_key"],
        }

    async def get_credentials(self, email: str, password: str) -> dict:
        """Get Sipuni credentials only (no service activation)."""
        result = await self._call_worker(
            "get_credentials",
            email=email,
            password=password,
        )

        return {
            "user_id": result["user_id"],
            "secret_key": result["secret_key"],
        }

    async def close(self):
        """No-op."""
        pass
