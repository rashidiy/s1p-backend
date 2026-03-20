"""
Async Sipuni Dashboard API Client

Ported from repos/s1p-automations/scripts/sipuni_api.py for use inside FastAPI.
Pure HTTP client — authenticates via session cookies, extracts credentials,
manages webhooks, and controls integration services.

Used once during setup flow. No persistent sessions — each setup is a fresh login.
Password is never stored.
"""

import re
import logging
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


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


class SipuniAsyncClient:
    """Async HTTP client for the Sipuni dashboard.

    All methods communicate with sipuni.com using standard HTTP requests
    and session cookies. Instantiated per-request — no singleton needed.
    """

    BASE = "https://sipuni.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=60,
            http2=False,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

    async def login(self, email: str, password: str) -> bool:
        """Authenticate with the Sipuni dashboard.

        Returns True if login succeeded, False otherwise.
        """
        login_page = await self.client.get(f"{self.BASE}/ru_RU/login")

        token_match = re.search(r'name="token"\s+value="([^"]*)"', login_page.text)
        csrf_match = re.search(r'login\[_token\]"\s+value="([^"]*)"', login_page.text)

        resp = await self.client.post(
            f"{self.BASE}/ru_RU/login",
            data={
                "returnUrl": "",
                "token": token_match.group(1) if token_match else "",
                "login[username_email]": email,
                "login[password]": password,
                "login[_token]": csrf_match.group(1) if csrf_match else "",
            },
        )

        if "/login" in str(resp.url):
            return False

        return True

    async def get_credentials(self) -> dict:
        """Extract Sipuni API credentials from the settings page.

        Returns dict with "user_id" and "secret_key" string values.
        """
        resp = await self.client.get(f"{self.BASE}/ru_RU/settings/integration")
        html = resp.text

        user_id = ""
        secret_key = ""

        id_match = re.search(r'№\s*(\d+)', html)
        if id_match:
            user_id = id_match.group(1)

        secret_match = re.search(r'name="secret"\s+value="([^"]*)"', html)
        if not secret_match:
            secret_match = re.search(
                r'Ключ интеграции.*?value="([^"]*)"', html, re.DOTALL
            )
        if secret_match:
            secret_key = secret_match.group(1)

        return {"user_id": user_id, "secret_key": secret_key}

    async def _get_stream_page(self) -> str:
        """Fetch the raw HTML of the stream settings page."""
        resp = await self.client.get(
            f"{self.BASE}/ru_RU/settings/integration/crm_http_api"
        )
        return resp.text

    async def _get_integration_page(self, slug: str) -> str:
        """Fetch the HTML for a specific integration tab."""
        resp = await self.client.get(
            f"{self.BASE}/ru_RU/settings/integration/{slug}"
        )
        return resp.text

    async def _is_service_enabled(self, slug: str) -> bool:
        """Check if an integration service is currently enabled."""
        return "Отключить услугу" in await self._get_integration_page(slug)

    async def _enable_service(self, slug: str) -> bool:
        """Enable an integration service by following its activation link."""
        html = await self._get_integration_page(slug)

        if "Отключить услугу" in html:
            return True

        enable_match = re.search(
            r'href="([^"]*)"[^>]*>\s*Подключить услугу', html
        )
        if enable_match:
            url = enable_match.group(1)
            if not url.startswith("http"):
                url = f"{self.BASE}{url}"
            await self.client.get(url)
            return await self._is_service_enabled(slug)

        return False

    async def enable_stream_api(self) -> bool:
        """Enable the stream/webhook service (События на АТС)."""
        return await self._enable_service("crm_http_api")

    async def enable_callback(self) -> bool:
        """Enable the callback API (Звонок на номер)."""
        return await self._enable_service("callback_api")

    async def list_webhooks(self) -> list[dict]:
        """List all configured webhook URLs on the stream settings page."""
        html = await self._get_stream_page()

        if "Подключить услугу" in html:
            return []

        webhooks = []
        for match in re.finditer(
            r'name="(\d+)\[url\]"[^>]*value="([^"]*)"', html
        ):
            webhooks.append({"id": match.group(1), "url": match.group(2)})

        return webhooks

    async def add_webhook(self, webhook_url: str, scheme: str = "all") -> bool:
        """Add a single webhook URL to the stream configuration.

        Automatically enables the stream service if disabled.
        """
        if not await self._is_service_enabled("crm_http_api"):
            await self.enable_stream_api()

        html = await self._get_stream_page()
        webhooks = await self.list_webhooks()

        existing_urls = {wh["url"] for wh in webhooks}
        if webhook_url in existing_urls:
            return True

        # Preserve all existing entries
        form_data = []
        for wh in webhooks:
            if wh["url"]:
                form_data.append((f"{wh['id']}[url]", wh["url"]))
                form_data.append((f"{wh['id']}[tree][]", "all"))

        # Fill empty slot or create new one
        empty_slots = [wh for wh in webhooks if not wh["url"]]
        if empty_slots:
            slot = empty_slots[0]
            form_data.append((f"{slot['id']}[url]", webhook_url))
            form_data.append((f"{slot['id']}[tree][]", scheme))
        else:
            length_match = re.search(r'data-length="(\d+)"', html)
            next_id = (
                int(length_match.group(1)) + 1
                if length_match
                else len(webhooks) + 1
            )
            form_data.append((f"{next_id}[url]", webhook_url))
            form_data.append((f"{next_id}[tree][]", scheme))

        body = urlencode(form_data)
        await self.client.post(
            f"{self.BASE}/ru_RU/settings/integration/crm_http_api",
            content=body.encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.BASE}/ru_RU/settings/integration/crm_http_api",
            },
        )

        updated_urls = {wh["url"] for wh in await self.list_webhooks()}
        return webhook_url in updated_urls

    async def full_setup(self, email: str, password: str, webhook_url: str) -> dict:
        """Run the complete Sipuni setup flow.

        Chains: login -> get_credentials -> enable_stream -> enable_callback -> add_webhook.

        Returns dict with "user_id" and "secret_key" on success.
        Raises specific error types on failure.
        """
        ok = await self.login(email, password)
        if not ok:
            raise LoginFailed("Login failed. Check email and password.")

        creds = await self.get_credentials()
        if not creds["user_id"] or not creds["secret_key"]:
            raise CredentialsNotFound("Could not extract API credentials from Sipuni dashboard.")

        stream_ok = await self.enable_stream_api()
        if not stream_ok:
            raise ServiceEnableFailed("Failed to enable Stream API (call event webhooks).")

        callback_ok = await self.enable_callback()
        if not callback_ok:
            raise ServiceEnableFailed("Failed to enable Callback API (outbound calls).")

        webhook_ok = await self.add_webhook(webhook_url)
        if not webhook_ok:
            raise WebhookSetupFailed("Failed to add webhook URL to Sipuni.")

        return creds

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
