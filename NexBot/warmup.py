# -*- coding: utf-8 -*-
import sys, io
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""warmup.py -- Warm up the Myntra session for NexBot.

Exact same as: python myntra_check.py --warmup
But writes to myntra_bot_profile/ (the bot's dedicated profile).

Workflow:
    1. Stop the bot (Ctrl+C)
    2. python warmup.py   <- Chrome window opens
    3. Confirm /forgot page is loaded, solve any captcha
    4. Press ENTER
    5. python bot.py

No conflict with your regular Chrome -- myntra_bot_profile is separate.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent
STATE_FILE      = _NEXCHECKER_DIR / "myntra_state.json"
BOT_PROFILE_DIR = _NEXCHECKER_DIR / "myntra_bot_profile"


async def warmup(headless: bool = False) -> None:
    from playwright.async_api import async_playwright

    print("[*] Warmup -- profile:", BOT_PROFILE_DIR)
    BOT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        # Exact same as myntra_check.py open_context()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BOT_PROFILE_DIR),
            channel="chrome",
            headless=headless,
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-http2",
            ],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Exact same as myntra_check.py ensure_forgot_page()
        print("[*] Navigating to https://www.myntra.com/forgot ...")
        try:
            await page.goto(
                "https://www.myntra.com/forgot",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            await page.wait_for_timeout(2000)
        except Exception as e:
            print("[!] goto warning:", e)

        if not headless:
            print()
            print("[*] Chrome window is open.")
            print("    Confirm the Reset Password page is loaded.")
            print("    Solve any challenge if shown.")
            print()
            print("    Press ENTER when ready ...")
            await asyncio.get_event_loop().run_in_executor(None, input)
        else:
            await page.wait_for_timeout(5000)

        # Save state -- exact same as myntra_check.py warmup()
        await context.storage_state(path=str(STATE_FILE))
        await context.close()

    cookies = len(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("cookies", []))
    print("[+] Saved", cookies, "cookies ->", STATE_FILE.name)
    print("[+] Warmup complete. Start the bot:")
    print("      python bot.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    asyncio.run(warmup(headless=args.headless))


if __name__ == "__main__":
    main()
