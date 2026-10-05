#!/usr/bin/env python3
"""
Silent Amazon India registration check (no OTP / no SMS)
"""

import sys
import asyncio
from playwright.async_api import async_playwright

def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


async def check_amazon(mobile: str) -> dict:
    mobile = normalize_mobile(mobile)
    if len(mobile) != 10:
        return {"status": "ERROR", "mobile": mobile, "error": "Need exactly 10 digits"}

    email_field = f"+91{mobile}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            signin_url = (
                "https://www.amazon.in/ap/signin?"
                "openid.pape.max_auth_age=0&"
                "openid.return_to=https%3A%2F%2Fwww.amazon.in%2F&"
                "openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                "openid.assoc_handle=inflex&"
                "openid.mode=checkid_setup&"
                "openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                "openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
            )
            await page.goto(signin_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)

            # Fill mobile
            filled = False
            for sel in ["#ap_email_login", "#ap_email", "input[name='email']", "input[type='email']"]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.click()
                        await el.fill(email_field)
                        filled = True
                        break
                except Exception:
                    continue

            if not filled:
                title = await page.title()
                await browser.close()
                return {"status": "ERROR", "mobile": mobile, "error": f"email input not found (title={title})"}

            # Continue
            clicked = False
            for sel in ["#continue", "input#continue", "span.a-button-inner input[type='submit']", "input[type='submit']"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click()
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # try pressing Enter
                await page.keyboard.press("Enter")

            await page.wait_for_timeout(4000)

            url = page.url
            title = await page.title()
            content = await page.content()
            content_l = content.lower()
            
            # --- CVF / CAPTCHA challenge ---
            if "/ap/cvf/" in url.lower() or "authentication required" in title.lower():
                await browser.close()
                return {
                    "status": "CHALLENGE",
                    "mobile": mobile,
                    "url": url,
                    "title": title,
                    "note": "Amazon CVF/CAPTCHA – retry later or use proxy",
                }

            # Explicit element checks
            pwd_visible = False
            try:
                pwd_visible = await page.locator(
                    "#ap_password, input[name='password'], input[type='password']"
                ).count() > 0
            except Exception:
                pass

            create_account_visible = False
            try:
                create_account_visible = await page.locator(
                    "#createAccountSubmit, a[href*='register'], #ap_register_form"
                ).count() > 0
            except Exception:
                pass

            registered_signals = [
                "auth-password-missing-alert" in content_l,
                "forgot your password" in content_l,
                "forgot password" in content_l,
                "enter your password" in content_l,
                pwd_visible,
            ]

            not_registered_signals = [
                "create account" in content_l,
                "claim your account" in content_l,
                "looks like you're new" in content_l,
                "new to amazon" in content_l,
                "/ap/register" in url.lower(),
                "ap_register" in content_l,
                create_account_visible,
                "let's create an account" in content_l,
            ]

            is_reg = any(registered_signals)
            is_not = any(not_registered_signals)

            await browser.close()

            if is_reg and not is_not:
                return {"status": "REGISTERED", "mobile": mobile, "url": url}
            if is_not and not is_reg:
                return {"status": "NOT_REGISTERED", "mobile": mobile, "url": url}
            if is_reg:
                return {"status": "REGISTERED", "mobile": mobile, "url": url}
            if is_not:
                return {"status": "NOT_REGISTERED", "mobile": mobile, "url": url}

            return {
                "status": "UNKNOWN",
                "mobile": mobile,
                "url": url,
                "title": title,
                "pwd_visible": pwd_visible,
                "create_visible": create_account_visible,
            }
         
        except Exception as e:
            try:
                await browser.close()
            except Exception:
                pass
            return {"status": "ERROR", "mobile": mobile, "error": str(e)}


def pretty_print(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")

    if status == "REGISTERED":
        print(f"""
❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟡 ᴀᴍᴀᴢᴏɴ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
🎯 Active Amazon account detected.
""")
    elif status == "NOT_REGISTERED":
        print(f"""
❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟡 ᴀᴍᴀᴢᴏɴ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
✅ No active Amazon account on this number.
""")
    else:
        print("Result:", result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python amazon_check.py <10-digit-mobile>")
        sys.exit(1)

    number = sys.argv[1]
    result = asyncio.run(check_amazon(number))
    pretty_print(result)