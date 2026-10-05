"""NexBot -- Myntra checker.

Uses the EXACT same technique as the working myntra_check.py:
  - channel="chrome"  (real Google Chrome, not Playwright Chromium)
  - launch_persistent_context with myntra_bot_profile/
  - ensure_forgot_page() -> api_call() -> check_with_heal()
  - Same decide() logic, same HEAL_WAIT

Profile: myntra_bot_profile/  (separate from user's Chrome profile -- no ProcessSingleton)
Warmup:  warmup.py opens the same profile headed so the user can confirm the page.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent.parent
STATE_FILE      = _NEXCHECKER_DIR / "myntra_state.json"
BOT_PROFILE_DIR = _NEXCHECKER_DIR / "myntra_bot_profile"   # dedicated bot profile

HEAL_WAIT = 3.0   # seconds -- same as myntra_check.py


# ── Helpers -- identical to myntra_check.py ───────────────────────────────────

def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def decide(http_status: int, data: Any) -> str:
    """Decode Myntra forgetpassword API response into REGISTERED/NOT_REGISTERED/CHALLENGE/UNKNOWN."""
    if not isinstance(data, dict):
        return "UNKNOWN"

    # ── Explicit challenge signals ────────────────────────────────────────────
    if data.get("sec-cp-challenge") or data.get("provider") == "crypto" or http_status == 428:
        return "CHALLENGE"

    # ── JSON parse failed → body was HTML (CF challenge, bot-detection page) ─
    # data only contains "raw_text" when JSON.parse() threw — i.e., we got HTML.
    raw_text = data.get("raw_text", "")
    if list(data.keys()) == ["raw_text"]:
        # HTML challenge indicators
        lower = raw_text.lower()
        if any(x in lower for x in ("<html", "challenge", "captcha", "cloudflare", "cf-ray",
                                     "just a moment", "checking your browser", "enable javascript")):
            return "CHALLENGE"
        # Unknown HTML we can't interpret — don't claim REGISTERED
        return "UNKNOWN"

    # ── Real JSON API response ────────────────────────────────────────────────
    code = data.get("code")
    msg  = (data.get("message") or "").lower()
    if code == 2002 or "does not exist" in msg:
        return "NOT_REGISTERED"
    if code == 2030:
        return "REGISTERED"
    if http_status == 200:
        # Real API: 200 with JSON body = OTP sent = user exists
        # Only safe here because we already ruled out raw_text-only (HTML) responses above
        return "REGISTERED"
    if any(x in msg for x in ("email", "password", "otp", "recover")) and "does not exist" not in msg:
        return "REGISTERED"
    return "UNKNOWN"


async def _open_context(playwright):
    """Launch persistent Chrome/Chromium context.
    - Windows: real Google Chrome (channel='chrome'), headless=False
    - Linux:   Playwright Chromium (channel=''), headless=True (no display)
    """
    import sys
    is_linux = sys.platform.startswith("linux")
    BOT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(BOT_PROFILE_DIR),
        channel="" if is_linux else "chrome",   # Linux: bundled chromium; Windows: real Chrome
        headless=is_linux,                        # Linux: headless; Windows: headed (avoids CF block)
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-http2",
            "--window-position=-10000,-10000",  # park off-screen -- won't bother you
        ],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def _ensure_forgot_page(page) -> None:
    """Exact copy of myntra_check.py ensure_forgot_page()."""
    try:
        await page.goto(
            "https://www.myntra.com/forgot",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await page.wait_for_timeout(2000)
    except Exception as e:
        logger.warning("[Myntra] goto warning: %s", e)


async def _api_call(page, mobile: str) -> Dict[str, Any]:
    """Exact copy of myntra_check.py api_call() -- fetch inside page."""
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

    data        = api.get("json") or {"raw_text": api.get("text", "")}
    http_status = api.get("http") or 0
    status      = decide(http_status, data if isinstance(data, dict) else {})

    # Log raw response for debugging — critical for catching CF/HTML responses on AWS
    logger.debug(
        "[Myntra] mobile=%s http=%s status=%s raw_keys=%s snippet=%.120s",
        mobile, http_status, status, list(data.keys()) if isinstance(data, dict) else "?",
        str(data),
    )
    if status == "CHALLENGE":
        logger.warning(
            "[Myntra] CHALLENGE on mobile=%s http=%s raw=%.200s",
            mobile, http_status, str(data),
        )

    return {
        "status": status,
        "mobile": mobile,
        "http":   http_status,
        "raw":    data,
        "via":    "playwright",
    }


async def _check_with_heal(page, mobile: str, max_heal: int = 2) -> Dict[str, Any]:
    """Exact copy of myntra_check.py check_with_heal()."""
    last = None
    for attempt in range(1, max_heal + 1):
        r    = await _api_call(page, mobile)
        last = r
        if r.get("status") in ("REGISTERED", "NOT_REGISTERED"):
            return r
        if r.get("status") == "CHALLENGE":
            logger.info("[Myntra] CHALLENGE heal %d/%d -- reload /forgot", attempt, max_heal)
            await _ensure_forgot_page(page)
            await page.wait_for_timeout(int(HEAL_WAIT * 1000))
            continue
        if r.get("status") == "ERROR":
            await _ensure_forgot_page(page)
            await page.wait_for_timeout(1500)
            continue
        break
    return last or {"status": "ERROR", "mobile": mobile, "error": "no result"}


# ── Bot singleton -- ONE persistent Chrome context for the whole session ───────

class MyntraChecker:
    """Manages ONE persistent Chrome context -- same as myntra_check.py run_bulk()."""

    def __init__(self) -> None:
        self._playwright = None
        self._context    = None
        self._page       = None
        self._lock       = asyncio.Lock()
        self._ready      = False

    async def startup(self) -> None:
        """Open real Chrome context + navigate to /forgot. Same as run_bulk() init."""
        if self._ready:
            return
        logger.info("[Myntra] Starting Chrome context (headless, myntra_bot_profile)...")
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._context, self._page = await _open_context(self._playwright)
            await _ensure_forgot_page(self._page)   # same as run_bulk()
            self._ready = True
            logger.info("[Myntra] Ready -- %s", BOT_PROFILE_DIR.name)
        except Exception as exc:
            logger.error("[Myntra] Failed to start: %s", exc)
            self._ready = False

    async def shutdown(self) -> None:
        """Persist cookies and close -- same as run_bulk() teardown."""
        if self._context:
            try:
                await self._context.storage_state(path=str(STATE_FILE))
                logger.info("[Myntra] State saved -> %s", STATE_FILE.name)
            except Exception as exc:
                logger.warning("[Myntra] Could not save state: %s", exc)
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

    async def check_number(self, mobile: str) -> Dict[str, Any]:
        """Check mobile. asyncio.Lock -- one check at a time (page is not concurrent-safe)."""
        if not self._ready or self._page is None:
            return {
                "status": "ERROR",
                "mobile": mobile,
                "http":   0,
                "raw":    {},
                "error":  "Chrome not ready -- run warmup.py first",
            }
        async with self._lock:
            return await _check_with_heal(self._page, mobile)

    async def reload_page(self) -> None:
        if self._ready and self._page:
            async with self._lock:
                await _ensure_forgot_page(self._page)

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Module singleton ──────────────────────────────────────────────────────────
myntra_checker = MyntraChecker()
