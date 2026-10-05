#!/usr/bin/env python3
"""
Zepto registration probe (no OTP code required)
Opens login, submits mobile, reads auth API JSON.
May trigger SMS on the number — does not need the code.
"""

import sys
import asyncio
import json
from playwright.async_api import async_playwright


def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def parse_status(payload) -> str | None:
    if payload is None:
        return None
    try:
        text = json.dumps(payload).lower() if not isinstance(payload, str) else payload.lower()
    except Exception:
        text = str(payload).lower()

    # NOT registered
    if any(s in text for s in [
        '"isnewuser": true', '"is_new_user": true', '"isnewuser":true',
        '"newuser": true', '"user_exists": false', '"userexists": false',
        '"exists": false', '"registered": false', '"account_exists": false',
    ]):
        if any(s in text for s in ['"isnewuser": false', '"is_new_user": false', '"userexists": true']):
            return "REGISTERED"
        return "NOT_REGISTERED"

    # Registered
    if any(s in text for s in [
        '"isnewuser": false', '"is_new_user": false', '"isnewuser":false',
        '"user_exists": true', '"userexists": true', '"exists": true',
        '"registered": true', '"account_exists": true',
    ]):
        return "REGISTERED"

    def walk(obj):
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


async def check_zepto(mobile: str, headless: bool = True) -> dict:
    mobile = normalize_mobile(mobile)
    if len(mobile) != 10:
        return {"status": "ERROR", "mobile": mobile, "error": "Need 10 digits"}

    captured = []

    async with async_playwright() as p:
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
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()

        async def on_response(response):
            try:
                url = response.url.lower()
                if any(x in url for x in (
                    "otp", "auth", "login", "user", "signup", "register",
                    "bff-gateway", "session", "verify",
                )):
                    ctype = (response.headers.get("content-type") or "").lower()
                    body = None
                    if "json" in ctype or "bff" in url or "api" in url:
                        try:
                            body = await response.json()
                        except Exception:
                            try:
                                body = await response.text()
                            except Exception:
                                body = None
                    if body is not None:
                        captured.append({
                            "url": response.url,
                            "status": response.status,
                            "body": body,
                        })
            except Exception:
                pass

        page.on("response", on_response)

        try:
            await page.goto(
                "https://www.zepto.com/auth/login",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(2500)

            # Fill mobile
            filled = False
            for sel in [
                "input[type='tel']",
                "input[name*='mobile']",
                "input[name*='phone']",
                "input[placeholder*='Mobile']",
                "input[placeholder*='mobile']",
                "input[placeholder*='Phone']",
                "input[inputmode='numeric']",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.click()
                        await el.fill(mobile)
                        filled = True
                        break
                except Exception:
                    continue

            if not filled:
                await browser.close()
                return {
                    "status": "ERROR",
                    "mobile": mobile,
                    "error": "mobile input not found",
                    "raw": captured[:3],
                }

            # Continue / Get OTP
            for sel in [
                "button:has-text('Continue')",
                "button:has-text('Get OTP')",
                "button:has-text('Send OTP')",
                "button:has-text('Login')",
                "button[type='submit']",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click(timeout=3000)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(4000)

            for item in captured:
                st = parse_status(item.get("body"))
                if st:
                    await browser.close()
                    return {
                        "status": st,
                        "mobile": mobile,
                        "via": "network",
                        "raw": item,
                    }

            # UI fallback
            content = (await page.content()).lower()
            if any(x in content for x in ("enter otp", "verify otp", "resend otp")):
                # OTP screen alone is weak — often shown for both
                pass
            if any(x in content for x in ("new to zepto", "create account", "sign up")):
                await browser.close()
                return {"status": "NOT_REGISTERED", "mobile": mobile, "via": "ui"}

            await browser.close()
            return {
                "status": "UNKNOWN",
                "mobile": mobile,
                "raw": captured[:6],
                "note": "Paste raw JSON to tune field names",
            }

        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"status": "ERROR", "mobile": mobile, "error": str(e), "raw": captured[:3]}


def pretty_print(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")
    if status == "REGISTERED":
        print(f"""
❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟣 ᴢᴇᴘᴛᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
""")
    elif status == "NOT_REGISTERED":
        print(f"""
❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟣 ᴢᴇᴘᴛᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
""")
    else:
        print("Result:", result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python zepto_check.py <10-digit-mobile>")
        sys.exit(1)
    result = asyncio.run(check_zepto(sys.argv[1], headless=True))
    pretty_print(result)