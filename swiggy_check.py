#!/usr/bin/env python3
"""
Silent Swiggy registration check (no OTP / no SMS)
"""

import sys
import asyncio
from playwright.async_api import async_playwright

def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits

async def check_swiggy(mobile: str) -> dict:
    mobile = normalize_mobile(mobile)
    
    if len(mobile) != 10:
        return {"status": "ERROR", "mobile": mobile, "error": "Need exactly 10 digits"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        
        try:
            await page.goto("https://www.swiggy.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
            
            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const res = await fetch('https://www.swiggy.com/dapi/auth/signin-with-check', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json',
                                '__fetch_req__': 'true',
                                'Platform': 'dweb'
                            }},
                            body: JSON.stringify({{
                                mobile: '{mobile}',
                                password: '',
                                _csrf: window._csrfToken || ''
                            }})
                        }});
                        return await res.json();
                    }} catch (e) {{
                        return {{ error: e.toString() }};
                    }}
                }}
            """)
            
            await browser.close()
            
            if isinstance(result, dict):
                data = result.get("data") or {}
                registered = data.get("registered")
                
                if registered is True:
                    return {
                        "status": "REGISTERED",
                        "mobile": mobile,
                        "verified": data.get("verified"),
                        "active": data.get("active"),
                        "raw": result
                    }
                if registered is False:
                    return {
                        "status": "NOT_REGISTERED",
                        "mobile": mobile,
                        "raw": result
                    }
                
                # fallback on statusMessage
                msg = str(result.get("statusMessage", "")).lower()
                if "already exists" in msg:
                    return {"status": "REGISTERED", "mobile": mobile, "raw": result}
                if "invalid mobile" in msg:
                    return {"status": "ERROR", "mobile": mobile, "error": "Invalid mobile number", "raw": result}
                
                return {"status": "UNKNOWN", "mobile": mobile, "raw": result}
            
            return {"status": "ERROR", "mobile": mobile, "raw": result}
            
        except Exception as e:
            await browser.close()
            return {"status": "ERROR", "mobile": mobile, "error": str(e)}


def pretty_print(result: dict):
    status = result.get("status")
    mobile = result.get("mobile")
    
    if status == "REGISTERED":
        print(f"""
❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟠 ꜱᴡɪɢɢʏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
🎯 Active Swiggy account detected.
""")
    elif status == "NOT_REGISTERED":
        print(f"""
❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🟠 ꜱᴡɪɢɢʏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
✅ No active Swiggy account on this number.
""")
    else:
        print("Result:", result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python swiggy_check.py <10-digit-mobile>")
        sys.exit(1)
    
    number = sys.argv[1]
    result = asyncio.run(check_swiggy(number))
    pretty_print(result)