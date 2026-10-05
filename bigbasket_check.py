#!/usr/bin/env python3
"""
BigBasket registration check — HTTP-first approach
1. Loads Akamai session cookies from bb_state.json (saved by bb_save_state.py)
2. Makes direct HTTP POST to mapi OTP endpoint (no browser fingerprint)
3. Falls back to real Chrome (channel="chrome") if HTTP is blocked

Usage:
    python bb_save_state.py          # one-time: save session
    python bigbasket_check.py <mobile>
"""

import sys
import asyncio
import json
import os
import random
from playwright.async_api import async_playwright

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bb_state.json")

MAPI_URLS = [
    "https://www.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/",
    "https://www.bigbasket.com/mapi/v3.4.0/member-svc/otp/send/",
]

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Channel": "BB-WEB",
    "X-Caller": "DVAR-SVC",
    "Referer": "https://www.bigbasket.com/",
    "Origin": "https://www.bigbasket.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def load_state() -> dict | None:
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def state_to_cookie_header(state: dict) -> tuple[str, str | None]:
    """Convert Playwright storage state cookies into a Cookie header string."""
    cookies = state.get("cookies", [])
    bb_cookies = [c for c in cookies if "bigbasket.com" in c.get("domain", "")]
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in bb_cookies)
    csrf = next(
        (c["value"] for c in bb_cookies if c["name"].lower() in ("csrftoken", "csrf_token", "_csrf")),
        None,
    )
    return cookie_str, csrf


def parse_registration(payload) -> str | None:
    if payload is None:
        return None
    try:
        text = json.dumps(payload).lower() if not isinstance(payload, str) else payload.lower()
    except Exception:
        text = str(payload).lower()

    if any(s in text for s in [
        '"is_new_user": true', '"is_new_user":true',
        '"user_exists": false', '"exists": false',
        '"is_registered": false', '"registered": false',
    ]):
        if '"is_new_user": false' in text or '"is_new_user":false' in text:
            return "REGISTERED"
        return "NOT_REGISTERED"

    if any(s in text for s in [
        '"is_new_user": false', '"is_new_user":false',
        '"user_exists": true', '"exists": true',
        '"is_registered": true', '"registered": true',
    ]):
        return "REGISTERED"

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                if kl in ("is_new_user", "new_user"):
                    if v is True:
                        return "NOT_REGISTERED"
                    if v is False:
                        return "REGISTERED"
                if kl in ("user_exists", "exists", "is_registered", "registered", "account_exists"):
                    if v is True:
                        return "REGISTERED"
                    if v is False:
                        return "NOT_REGISTERED"
                r = walk(v)
                if r:
                    return r
        elif isinstance(obj, list):
            for i in obj:
                r = walk(i)
                if r:
                    return r
        return None

    return walk(payload) if not isinstance(payload, str) else None


# ── Method 1: Pure HTTP with httpx (no browser) ───────────────────────────────

async def check_via_http(mobile: str, state: dict) -> dict:
    """Direct HTTP POST using cookies from saved Chrome session."""
    try:
        import httpx
    except ImportError:
        return {"status": "SKIP", "reason": "httpx not installed (pip install httpx)"}

    cookie_str, csrf = state_to_cookie_header(state)
    if not cookie_str:
        return {"status": "SKIP", "reason": "No bigbasket.com cookies in state file"}

    headers = {**BASE_HEADERS}
    if cookie_str:
        headers["Cookie"] = cookie_str
    if csrf:
        headers["X-CSRFToken"] = csrf

    body = json.dumps({"identifier": mobile, "mobile_no": mobile}).encode()

    async with httpx.AsyncClient(timeout=20, verify=False) as client:
        for url in MAPI_URLS:
            try:
                resp = await client.post(url, content=body, headers=headers)
                if resp.status_code == 403:
                    continue
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text
                st = parse_registration(data)
                if st:
                    return {
                        "status": st,
                        "mobile": mobile,
                        "via": "http_direct",
                        "http_status": resp.status_code,
                        "raw": data,
                    }
            except Exception as e:
                continue

    return {"status": "UNKNOWN", "mobile": mobile, "via": "http_direct", "reason": "No conclusive response"}


# ── Method 2: Real Chrome (channel="chrome") with saved state ─────────────────

async def check_via_real_chrome(mobile: str, state_path: str) -> dict:
    """Use real installed Chrome with saved Akamai session."""
    captured = []

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            # Chrome not found or headless not supported, try headful
            try:
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as e2:
                return {"status": "ERROR", "mobile": mobile, "error": f"Chrome not found: {e2}"}

        context = await browser.new_context(
            storage_state=state_path,
            user_agent=BASE_HEADERS["User-Agent"],
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            ignore_https_errors=True,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        page = await context.new_page()

        async def on_response(response):
            try:
                url = response.url.lower()
                if any(x in url for x in ("member-svc", "otp", "login", "auth", "mapi")):
                    try:
                        body = await response.json()
                    except Exception:
                        try:
                            body = await response.text()
                        except Exception:
                            body = None
                    captured.append({"url": response.url, "status": response.status, "body": body})
            except Exception:
                pass

        page.on("response", on_response)

        try:
            resp = await page.goto(
                "https://www.bigbasket.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(2000)

            home_status = resp.status if resp else None
            title = await page.title()
            preview = (await page.content())[:500].lower()

            if home_status in (403, 429) or "access denied" in preview or "access denied" in title.lower():
                await browser.close()
                return {
                    "status": "PROXY_BLOCKED",
                    "mobile": mobile,
                    "via": "real_chrome",
                    "home_status": home_status,
                    "title": title,
                }

            cookies = await context.cookies()
            csrf = next(
                (c["value"] for c in cookies if c.get("name", "").lower() in ("csrftoken", "csrf_token", "_csrf")),
                None,
            )

            api_result = await page.evaluate(
                """async ({ mobile, csrf }) => {
                    const headers = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-Channel': 'BB-WEB',
                        'X-Caller': 'DVAR-SVC',
                        'Referer': 'https://www.bigbasket.com/',
                        'Origin': 'https://www.bigbasket.com'
                    };
                    if (csrf) headers['X-CSRFToken'] = csrf;
                    const urls = [
                        'https://www.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/',
                        'https://www.bigbasket.com/mapi/v3.4.0/member-svc/otp/send/',
                    ];
                    const out = [];
                    for (const url of urls) {
                        try {
                            const res = await fetch(url, {
                                method: 'POST',
                                headers,
                                body: JSON.stringify({ identifier: mobile, mobile_no: mobile })
                            });
                            const text = await res.text();
                            let json = null;
                            try { json = JSON.parse(text); } catch (e) {}
                            out.push({ url, http: res.status, json, text: text.slice(0, 500) });
                        } catch (e) {
                            out.push({ url, error: e.toString() });
                        }
                    }
                    return out;
                }""",
                {"mobile": mobile, "csrf": csrf},
            )

            for item in (api_result or []):
                if item.get("http") == 403:
                    continue
                st = parse_registration(item.get("json") or item.get("text"))
                if st:
                    await browser.close()
                    return {"status": st, "mobile": mobile, "via": "real_chrome_api", "raw": item}

            for item in captured:
                if item.get("status") == 403:
                    continue
                st = parse_registration(item.get("body"))
                if st:
                    await browser.close()
                    return {"status": st, "mobile": mobile, "via": "real_chrome_network", "raw": item}

            await browser.close()
            return {
                "status": "UNKNOWN",
                "mobile": mobile,
                "via": "real_chrome",
                "home_status": home_status,
                "title": title,
                "raw": (api_result or [])[:2],
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"status": "ERROR", "mobile": mobile, "via": "real_chrome", "error": str(e)}


# ── Main orchestrator ─────────────────────────────────────────────────────────

async def check_bigbasket(mobile: str) -> dict:
    mobile = normalize_mobile(mobile)
    if len(mobile) != 10:
        return {"status": "ERROR", "mobile": mobile, "error": "Need exactly 10 digits"}

    state = load_state()
    if not state:
        print("[!] bb_state.json not found — run bb_save_state.py first!", flush=True)
        return {
            "status": "BLOCKED",
            "mobile": mobile,
            "message": "No saved session. Run bb_save_state.py first.",
        }

    # --- Method 1: Direct HTTP (fastest, no browser overhead) ---
    print("[*] Trying direct HTTP with saved session cookies...", flush=True)
    r = await check_via_http(mobile, state)
    if r.get("status") in ("REGISTERED", "NOT_REGISTERED"):
        return r
    print(f"[-] HTTP method: {r.get('status')} — {r.get('reason', r.get('error', ''))}", flush=True)

    # --- Method 2: Real Chrome with saved state ---
    print("[*] Trying real Chrome (channel=chrome) with saved state...", flush=True)
    r = await check_via_real_chrome(mobile, STATE_FILE)
    if r.get("status") in ("REGISTERED", "NOT_REGISTERED"):
        return r
    print(f"[-] Real Chrome method: {r.get('status')}", flush=True)

    return r


def pretty_print(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")
    via = result.get("via", "unknown")

    if status == "REGISTERED":
        print(f"""
\u2770 \u2705 \U0001d97d\U0001d9c2\U0001d9b4\U0001d97f\U0001d9c0\U0001d9c3\U0001d9c1 \U0001d9d5\U0001d9be\U0001d9c0\U0001d9c2\U0001d9c3 \U0001f3af \u2771
\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513
\u2713 STATUS: REGISTERED
\U0001f3af PLATFORM: BigBasket
\U0001f4f1 NUMBER: {mobile}
\U0001f310 VIA: {via}
\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b
""")
    elif status == "NOT_REGISTERED":
        print(f"""
\u2770 \u274c \U0001d9b3\U0001d9be\U0001d9c1 \U0001d9c0\U0001d9c1\U0001d9be\U0001d9b7\U0001d9be\U0001d9c0\U0001d9c1\U0001d9c1\U0001d9c1\U0001d9c1 \u2771
\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513
\u2717 STATUS: NOT REGISTERED
\U0001f3af PLATFORM: BigBasket
\U0001f4f1 NUMBER: {mobile}
\U0001f310 VIA: {via}
\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b
""")
    elif status in ("BLOCKED", "PROXY_BLOCKED"):
        print(f"""
\u2770 \u26a0\ufe0f BLOCKED \u2771
\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513
\u26a0 PLATFORM: BigBasket (Akamai block)
\U0001f4f1 NUMBER: {mobile}
\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b
Session expired. Run bb_save_state.py again.
""")
    else:
        print("Result:", result)
#!/usr/bin/env python3
"""
One-time: open BigBasket in your REAL Chrome, pass Akamai, save storage state.

Run once:
    python bb_save_state.py

Creates bb_state.json — used automatically by bigbasket_check.py.

Requires Google Chrome to be installed (uses channel="chrome").
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bb_state.json")


def log(msg: str):
    print(msg)
    sys.stdout.flush()


async def main():
    log("[*] Launching your installed Google Chrome (not headless Chromium)...")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                channel="chrome",   # <-- uses your real Chrome, not Playwright's Chromium
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        except Exception as e:
            log(f"[!] Could not find Chrome: {e}")
            log("[!] Falling back to Playwright Chromium (may still be blocked)...")
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            ignore_https_errors=True,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        page = await context.new_page()
        log("[*] Opening https://www.bigbasket.com/ ...")
        await page.goto(
            "https://www.bigbasket.com/",
            wait_until="domcontentloaded",
            timeout=90000,
        )

        # Poll for Access Denied and report status
        for attempt in range(30):
            await page.wait_for_timeout(2000)
            title = await page.title()
            content = (await page.content())[:600].lower()
            if "access denied" in title.lower() or "access denied" in content:
                log(f"[!] Still 'Access Denied' (wait {attempt * 2}s)... press F5 in the browser.")
            else:
                log(f"[+] Homepage OK: {title}")
                break

        log("")
        log("====================================================")
        log(" BROWSER IS OPEN -- do the following:")
        log("")
        log(" 1. If still 'Access Denied': press F5 to reload.")
        log("    Real Chrome usually loads on the 1st try.")
        log(" 2. Wait until BigBasket loads fully")
        log("    (logo, search bar, Shop by Category visible).")
        log(" 3. Optional: click Login/Sign Up once.")
        log(" 4. Come back to THIS terminal and press ENTER.")
        log("====================================================")
        log("")
        input("Press ENTER after homepage looks normal -> ")

        await context.storage_state(path=STATE_FILE)
        log(f"[+] Saved session -> {STATE_FILE}")
        log("[+] Done! Now run:  python bigbasket_check.py <mobile>")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bigbasket_check.py <10-digit-mobile>")
        sys.exit(1)
    result = asyncio.run(check_bigbasket(sys.argv[1]))
    pretty_print(result)