import httpx, asyncio, re, subprocess, time

async def test():
    c = httpx.AsyncClient(follow_redirects=True, timeout=60, http2=False,
                          headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    lp = await c.get("https://sipuni.com/ru_RU/login")
    csrf = re.search(r'login\[_token\]"\s+value="([^"]*)"', lp.text)
    await c.post("https://sipuni.com/ru_RU/login", data={
        "returnUrl": "", "token": "",
        "login[username_email]": "alex.tot.samyy@gmail.com",
        "login[password]": "4890173fe",
        "login[_token]": csrf.group(1) if csrf else "",
    })
    cookies = dict(c.cookies)
    await c.aclose()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    print("Login OK, cookies:", list(cookies.keys()))

    def curl_get(url):
        r = subprocess.run(["curl", "-s", "-b", cookie_str, "-L", "--max-time", "15", url], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace")

    pages = [
        "https://sipuni.com/ru_RU/settings/integration",
        "https://sipuni.com/ru_RU/settings/integration/stream",
        "https://sipuni.com/ru_RU/settings/integration/callback",
        "https://sipuni.com/ru_RU/settings/integration/crm_http_api",
    ]
    for url in pages:
        t = time.time()
        html = curl_get(url)
        name = url.split("/")[-1]
        print(f"  {name}: {len(html)} bytes ({time.time()-t:.1f}s)")

    # Test credentials extraction
    html = curl_get("https://sipuni.com/ru_RU/settings/integration")
    id_m = re.search(r'\u2116\s*(\d+)', html)
    sec_m = re.search(r'name="secret"\s+value="([^"]*)"', html)
    print(f"Cabinet ID: {id_m.group(1) if id_m else 'NONE'}")
    print(f"Secret key: {sec_m.group(1)[:8] + '...' if sec_m else 'NONE'}")
    print("ALL DONE")

asyncio.run(test())
