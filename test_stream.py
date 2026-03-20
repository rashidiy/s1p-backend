import asyncio, re
from utils.services.sipuni_client import SipuniAsyncClient

async def test():
    client = SipuniAsyncClient()
    await client.login("test@example.com", "placeholder_password")

    html = client._curl_get("https://sipuni.com/ru_RU/settings/integration/stream")
    webhooks = re.findall(r'name="(\d+)\[url\]"[^>]*value="([^"]*)"', html)
    print(f"Webhooks found: {webhooks}")

    # Check what the page has
    for kw in ["webhook", "url", "HTTP", "api", "form", "Событ", "tree"]:
        c = html.lower().count(kw.lower())
        if c:
            print(f"  '{kw}': {c}x")

    # Credentials from integration page
    creds = client.get_credentials()
    print(f"Credentials: {creds}")

    print("Done")

asyncio.run(test())
