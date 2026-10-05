#!/usr/bin/env python3
"""
Zepto registration check (no OTP code required)
Uses real Chrome + AWS WAF wait + network intercept.

Usage:
  python zepto_check.py 9027936246
  python zepto_check.py 9027936246 9927936712
  python zepto_check.py --visible 9027936246
  python zepto_check.py --warmup
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

BASE = Path(__file__).resolve().parent
PROFILE_DIR = BASE / "zepto_chrome_profile"
STATE_FILE = BASE / "zepto_state.json"


def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def parse_status(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        text = json.dumps(payload).lower() if not isinstance(payload, str) else payload.lower()
    except Exception:
        text = str(payload).lower()

    # Skip pure WAF tokens
    if "token" in text and "awswaf" in text:
        return None
    if isinstance(payload, dict) and set(payload.keys()) <= {"token", "inputs"}:
        return None

    not_reg = [
        '"isnewuser": true',
        '"is_new_user": true',
        '"isnewuser":true',
        '"newuser": true',
        '"user_exists": false',
        '"userexists": false',
        '"exists": false',
        '"registered": false',
        '"account_exists": false',
        '"is_registered": false',
        "user not found",
        "account does not exist",
        "new user",
    ]
    is_reg = [
        '"isnewuser": false',
        '"is_new_user": false',
        '"isnewuser":false',
        '"user_exists": true',
        '"userexists": true',
        '"exists": true',
        '"registered": true',
        '"account_exists": true',
        '"is_registered": true',
        "otp sent",
        "otp_sent",
        "welcome back",
    ]

    if any(s in text for s in not_reg):
        if any(s in text for s in ['"isnewuser": false', '"is_new_user": false', '"userexists": true']):
            return "REGISTERED"
        return "NOT_REGISTERED"
    if any(s in text for s in is_reg):
        return "REGISTERED"

    def walk(obj: Any) -> str | None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower().replace("_", "")
                if kl in ("isnewuser", "newuser"):
                    if v is True:
                        return "NOT_REGISTERED"
                    if v is False:
                        return "REGISTERED"
                if kl in ("userexists", "exists", "registered", "accountexists", "isregistered"):
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

    if not isinstance(payload, str):
        return walk(payload)
    return None


async def open_context(p, headless: bool):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=headless,
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
    except Exception:
        # Fallback: bundled chromium
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
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
            storage_state=str(STATE_FILE) if STATE_FILE.exists() else None,
        )
        context._zepto_browser = browser  # type: ignore
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def wait_past_waf(page, timeout_ms: int = 25000) -> bool:
    """Wait until AWS WAF challenge finishes and real page content appears."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            url = page.url.lower()
            content = (await page.content()).lower()
            # Still on WAF interstitials
            if "awswaf" in url or "challenge" in url:
                await page.wait_for_timeout(800)
                continue
            if "access denied" in content and len(content) < 2000:
                await page.wait_for_timeout(800)
                continue
            # Look for login-ish UI
            for sel in [
                "input[type='tel']",
                "input[placeholder*='Mobile' i]",
                "input[placeholder*='mobile' i]",
                "input[placeholder*='Phone' i]",
                "input[inputmode='numeric']",
                "input[name*='mobile' i]",
                "input[name*='phone' i]",
            ]:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    try:
                        if await loc.first.is_visible():
                            return True
                    except Exception:
                        pass
            # page may still be loading SPA
            await page.wait_for_timeout(1000)
        except Exception:
            await page.wait_for_timeout(800)
    return False


async def fill_mobile(page, mobile: str) -> bool:
    selectors = [
        "input[type='tel']",
        "input[inputmode='numeric']",
        "input[placeholder*='Mobile' i]",
        "input[placeholder*='mobile' i]",
        "input[placeholder*='Phone' i]",
        "input[placeholder*='phone' i]",
        "input[name*='mobile' i]",
        "input[name*='phone' i]",
        "input[id*='mobile' i]",
        "input[id*='phone' i]",
        "input[type='number']",
        "input[type='text']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n):
                el = loc.nth(i)
                if not await el.is_visible():
                    continue
                await el.click(timeout=2000)
                await el.fill("")
                await el.fill(mobile)
                # verify
                val = await el.input_value()
                if mobile in val.replace(" ", "") or val.replace(" ", "").endswith(mobile[-8:]):
                    return True
                # try type
                await el.fill("")
                await el.type(mobile, delay=40)
                val = await el.input_value()
                if mobile[-8:] in val.replace(" ", ""):
                    return True
        except Exception:
            continue
    return False


async def click_continue(page) -> bool:
    for sel in [
        "button:has-text('Continue')",
        "button:has-text('CONTINUE')",
        "button:has-text('Get OTP')",
        "button:has-text('Send OTP')",
        "button:has-text('Login')",
        "button:has-text('LOGIN')",
        "div[role='button']:has-text('Continue')",
        "button[type='submit']",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(timeout=3000)
                return True
        except Exception:
            continue
    # keyboard submit
    try:
        await page.keyboard.press("Enter")
        return True
    except Exception:
        return False


async def check_one(page, mobile: str, captured: list) -> dict:
    # clear previous captures for this number
    before = len(captured)

    ok = await fill_mobile(page, mobile)
    if not ok:
        # dump helpful debug
        inputs = await page.evaluate(
            """() => Array.from(document.querySelectorAll('input')).map(i => ({
                type: i.type, name: i.name, id: i.id, placeholder: i.placeholder,
                visible: !!(i.offsetWidth || i.offsetHeight)
            }))"""
        )
        return {
            "status": "ERROR",
            "mobile": mobile,
            "error": "mobile input not found (WAF or layout change)",
            "inputs": inputs,
            "url": page.url,
        }

    await click_continue(page)
    await page.wait_for_timeout(4500)

    # parse new network bodies
    for item in captured[before:]:
        st = parse_status(item.get("body"))
        if st:
            return {
                "status": st,
                "mobile": mobile,
                "via": "network",
                "raw": item,
            }

    content = (await page.content()).lower()
    url = page.url.lower()

    if any(x in content for x in ("new to zepto", "create account", "sign up", "signup")):
        return {"status": "NOT_REGISTERED", "mobile": mobile, "via": "ui"}
    if any(x in content for x in ("enter otp", "verify otp", "resend otp", "otp sent")):
        # OTP screen is ambiguous — prefer network; weak signal only
        return {
            "status": "UNKNOWN",
            "mobile": mobile,
            "via": "ui_otp_screen",
            "note": "OTP UI shown; need API JSON fields",
            "raw": captured[before : before + 5],
        }

    return {
        "status": "UNKNOWN",
        "mobile": mobile,
        "url": url,
        "raw": captured[before : before + 6],
    }


async def run(numbers: list[str], headless: bool = True, warmup: bool = False) -> list[dict]:
    from playwright.async_api import async_playwright

    captured: list[dict] = []
    results: list[dict] = []

    async with async_playwright() as p:
        context, page = await open_context(p, headless=headless)

        async def on_response(response):
            try:
                url = response.url
                ul = url.lower()
                if any(
                    x in ul
                    for x in (
                        "otp",
                        "auth",
                        "login",
                        "user",
                        "signup",
                        "register",
                        "bff-gateway",
                        "session",
                        "verify",
                        "customer",
                    )
                ):
                    # skip pure waf noise unless useful
                    if "awswaf" in ul and "mp_verify" in ul:
                        return
                    body = None
                    try:
                        body = await response.json()
                    except Exception:
                        try:
                            t = await response.text()
                            if t and t.strip().startswith(("{", "[")):
                                body = json.loads(t)
                            else:
                                body = t[:400] if t else None
                        except Exception:
                            body = None
                    if body is not None:
                        captured.append({"url": url, "status": response.status, "body": body})
            except Exception:
                pass

        page.on("response", on_response)

        print("[*] Loading Zepto login (waiting for AWS WAF)...")
        try:
            await page.goto(
                "https://www.zepto.com/auth/login",
                wait_until="domcontentloaded",
                timeout=90000,
            )
        except Exception as e:
            print(f"[!] goto warning: {e}")

        ready = await wait_past_waf(page, timeout_ms=30000)
        if not ready:
            # try homepage then login
            try:
                await page.goto("https://www.zepto.com/", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                await page.goto(
                    "https://www.zepto.com/auth/login",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                ready = await wait_past_waf(page, timeout_ms=20000)
            except Exception as e:
                print(f"[!] retry warning: {e}")

        if warmup:
            print("    Warmup mode — confirm login page, press ENTER...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            try:
                await context.storage_state(path=str(STATE_FILE))
            except Exception:
                pass
            await context.close()
            if hasattr(context, "_zepto_browser"):
                await context._zepto_browser.close()  # type: ignore
            return [{"status": "WARMED", "note": "session saved"}]

        if not ready:
            # still try checks — sometimes inputs appear later
            print("[!] WAF/page may still be loading — attempting anyway")

        for i, raw in enumerate(numbers, 1):
            mobile = normalize_mobile(raw)
            print(f"[{i}/{len(numbers)}] {mobile} ...", end=" ", flush=True)
            if len(mobile) != 10:
                results.append({"status": "ERROR", "mobile": raw, "error": "bad number"})
                print("ERROR")
                continue

            # refresh login page between numbers to reset form
            if i > 1:
                try:
                    await page.goto(
                        "https://www.zepto.com/auth/login",
                        wait_until="domcontentloaded",
                        timeout=45000,
                    )
                    await wait_past_waf(page, timeout_ms=15000)
                except Exception:
                    pass

            r = await check_one(page, mobile, captured)
            results.append(r)
            print(r.get("status"))

            await page.wait_for_timeout(400)

        try:
            await context.storage_state(path=str(STATE_FILE))
        except Exception:
            pass
        await context.close()
        if hasattr(context, "_zepto_browser"):
            await context._zepto_browser.close()  # type: ignore

    return results


def pretty(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")
    if status == "REGISTERED":
        print(
            f"""
❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟣 ᴢᴇᴘᴛᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
"""
        )
    elif status == "NOT_REGISTERED":
        print(
            f"""
❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟣 ᴢᴇᴘᴛᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
"""
        )
    else:
        print("Result:", result)


def main():
    ap = argparse.ArgumentParser(description="Zepto registration checker")
    ap.add_argument("numbers", nargs="*")
    ap.add_argument("--visible", action="store_true", help="show browser")
    ap.add_argument("--warmup", action="store_true", help="visible session warm")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.warmup:
        asyncio.run(run([], headless=False, warmup=True))
        return

    if not args.numbers:
        print("Usage: python zepto_check.py [--visible] <mobile> [mobile2 ...]")
        print("       python zepto_check.py --warmup")
        sys.exit(1)

    headless = not args.visible
    results = asyncio.run(run(args.numbers, headless=headless))

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
