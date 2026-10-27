#!/usr/bin/env python3
"""
NexChecker — Zomato silent registration checker (no OTP sent to target).

Methods:
  1. Primary: Local or remote NexZomato HTTP checker endpoint (default: http://127.0.0.1:3000/api/checker/phone).
  2. Fallback: Direct Zomato contact-sync engine using local stored credentials.

Outputs standard unified status:
  - REGISTERED: Target phone is registered on Zomato
  - NOT_REGISTERED: Target phone is not registered / fresh
  - ERROR / UNKNOWN: Failed to determine status
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

# ------------------------------------------------------------
# Config & Endpoints
# ------------------------------------------------------------
CHECKERS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CHECKERS_DIR.parent

ZOMATO_CHECKER_URL = os.getenv(
    "ZOMATO_CHECKER_URL", "http://127.0.0.1:3000/api/checker/phone"
)

# Detect accounts directory in priority order:
# 1. ZOMATO_ACCOUNTS_DIR environment variable
# 2. In-repo directory: PROJECT_ROOT / "zomato_accounts"
# 3. In-repo data directory: PROJECT_ROOT / "data" / "zomato_accounts"
# 4. Sibling repo: PROJECT_ROOT.parent / "NexZomato" / "server" / "data" / "accounts"
def get_accounts_dir() -> Optional[Path]:
    env_dir = os.getenv("ZOMATO_ACCOUNTS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    candidates = [
        PROJECT_ROOT / "zomato_accounts",
        PROJECT_ROOT / "data" / "zomato_accounts",
        PROJECT_ROOT.parent / "NexZomato" / "server" / "data" / "accounts",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None

ZOMATO_API_BASE = "https://api.zomato.com"
SYNC_ENDPOINT = f"{ZOMATO_API_BASE}/gw/user-preference/recommendation/sync-contacts"
GET_ENDPOINT = f"{ZOMATO_API_BASE}/gw/user-preference/recommendation/get-contacts"

TIMEOUT = 12
BULK_DELAY = 0.4

DIGIT_TO_LETTER = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
LETTER_TO_DIGIT = {
    "A": "0", "B": "1", "C": "2", "D": "3", "E": "4",
    "F": "5", "G": "6", "H": "7", "I": "8", "J": "9",
}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def normalize_mobile(mobile: str) -> str:
    """Extract clean 10-digit Indian mobile number."""
    digits = "".join(c for c in str(mobile) if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif len(digits) > 10:
        digits = digits[-10:]
    return digits


def encode_phone_to_name(clean10: str) -> str:
    """Encode digits to alphabetic string to comply with Zomato naming rules."""
    code = "".join(DIGIT_TO_LETTER[int(d)] for d in clean10)
    return f"NexUser {code}"


def decode_name_to_phone(name: str) -> Optional[str]:
    """Decode alphabetic contact name back to 10-digit phone."""
    import re
    match = re.search(r"NexUser\s+([A-J]{10})", name or "", re.IGNORECASE)
    if not match:
        return None
    return "".join(LETTER_TO_DIGIT[c] for c in match.group(1).upper())


def pretty_print(result: dict) -> None:
    status = result.get("status", "UNKNOWN")
    mobile = result.get("mobile", "")
    recs = result.get("recommendations", 0)
    name = result.get("name", "")
    if status == "REGISTERED":
        print("❰ [OK] REGISTERED ❱")
        print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        print(f"✓ Status   : REGISTERED")
        print(f"🎯 Platform : Zomato 🍽")
        print(f"📱 Number   : {mobile}")
        if name:
            print(f"👤 Name     : {name}")
        if recs:
            print(f"📊 Recs     : {recs}")
        print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
        print("Active Zomato account detected.")
    elif status == "NOT_REGISTERED":
        print("❰ [X] NOT REGISTERED ❱")
        print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        print(f"✗ Status   : NOT_REGISTERED")
        print(f"🎯 Platform : Zomato 🍽")
        print(f"📱 Number   : {mobile}")
        print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
        print("No active Zomato account on this number.")
    else:
        print(f"Result: {result}")


# ------------------------------------------------------------
# Fallback Direct Account Resolver
# ------------------------------------------------------------
def _load_direct_tokens(limit: int = 5) -> List[str]:
    """Find valid logged-in Zomato account tokens from the accounts directory."""
    acc_dir = get_accounts_dir()
    if not acc_dir or not acc_dir.is_dir():
        return []

    tokens: List[str] = []
    json_files = list(acc_dir.glob("*.json"))
    for f in sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                token = (
                    data.get("accessToken")
                    or data.get("access_token")
                    or data.get("token")
                    or data.get("session", {}).get("accessToken")
                )
                if token and str(token) not in tokens:
                    tokens.append(str(token))
                    if len(tokens) >= limit:
                        break
        except Exception:
            continue
    return tokens


def _check_direct_contact_sync(m10: str, token: str) -> dict:
    """Execute direct Zomato contact-sync check with token."""
    encoded_name = encode_phone_to_name(m10)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.zomato.com",
        "Referer": "https://www.zomato.com/",
        "access_token": token,
        "x-access-token": token,
        "Authorization": f"Bearer {token}",
    }

    # 1. Sync contact
    try:
        sync_payload = {
            "flow_type": "revamped_flow",
            "contacts_access_level": "full_access",
            "contacts": [
                {
                    "phone_numbers": [f"+91{m10}", m10],
                    "name": encoded_name,
                    "id": "1",
                }
            ],
        }
        requests.post(SYNC_ENDPOINT, headers=headers, json=sync_payload, timeout=TIMEOUT)
    except Exception:
        pass

    # 2. Get contacts recommendations
    get_payload = {
        "request_type": "initial",
        "additional_filters": {},
        "page_type": "contacts_management",
        "removed_snippet_ids": [],
        "page_index": "1",
        "count": 100,
        "is_gold_mode_on": False,
        "keyword": "",
        "load_more": True,
    }

    try:
        r = requests.post(GET_ENDPOINT, headers=headers, json=get_payload, timeout=TIMEOUT)
        if r.status_code in (401, 403):
            return {"status": "AUTH_ERROR", "code": r.status_code}
        data = r.json() if r.status_code == 200 else {}
    except Exception as exc:
        return {"status": "ERROR", "mobile": m10, "error": str(exc)}

    snippets = data.get("results") or []
    for snippet in snippets:
        acc_items = snippet.get("accordion_snippet_type_15", {}).get("items") or []
        for acc in acc_items:
            checkbox_items = acc.get("checkbox_snippet_type_6", {}).get("items") or []
            for item in checkbox_items:
                contact_name = item.get("title", {}).get("text", "")
                subtitle = (item.get("subtitle", {}).get("text") or "").strip()
                matched = (
                    decode_name_to_phone(contact_name) == m10
                    or contact_name == encoded_name
                    or m10 in contact_name
                )
                if matched:
                    if "not on zomato" in subtitle.lower():
                        return {
                            "status": "NOT_REGISTERED",
                            "registered": False,
                            "mobile": m10,
                            "subtitle": subtitle,
                        }
                    # Extract owner name & recommendation count
                    owner_name = None
                    try:
                        deeplink = item.get("click_action", {}).get("deeplink", {}).get("url", "")
                        if "friend_recommendation_params=" in deeplink:
                            import urllib.parse
                            raw_p = urllib.parse.unquote(deeplink.split("friend_recommendation_params=")[1])
                            p_json = json.loads(raw_p)
                            if p_json.get("owner_user_name") and not p_json["owner_user_name"].startswith("NexUser"):
                                owner_name = p_json["owner_user_name"]
                    except Exception:
                        pass

                    rec_count = 1
                    try:
                        import re
                        m = re.search(r"(\d+)\s+recommendation", subtitle, re.I)
                        if m:
                            rec_count = int(m.group(1))
                    except Exception:
                        pass

                    return {
                        "status": "REGISTERED",
                        "registered": True,
                        "mobile": m10,
                        "subtitle": subtitle,
                        "name": owner_name or item.get("title", {}).get("text"),
                        "recommendations": rec_count,
                    }

    return {
        "status": "NOT_REGISTERED",
        "registered": False,
        "mobile": m10,
        "note": "Not found in Zomato registered contacts list",
    }
# ------------------------------------------------------------
# Core Check Function
# ------------------------------------------------------------
def check_zomato(mobile: str) -> dict:
    """Check if an Indian mobile number is registered on Zomato.

    Returns:
      {
        "status": "REGISTERED" | "NOT_REGISTERED" | "ERROR",
        "mobile": "9876543210",
        "registered": bool,
        ...
      }
    """
    m10 = normalize_mobile(mobile)
    if len(m10) != 10 or m10[0] not in "6789":
        return {
            "status": "ERROR",
            "mobile": mobile,
            "error": "Invalid 10-digit Indian mobile",
        }

    # Method 1: Local or remote NexZomato HTTP checker service
    try:
        resp = requests.post(
            ZOMATO_CHECKER_URL,
            json={"target_phone": m10},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            is_reg = bool(data.get("registered") or data.get("isZomatoUser"))
            return {
                "status": "REGISTERED" if is_reg else "NOT_REGISTERED",
                "registered": is_reg,
                "mobile": m10,
                "recommendations": data.get("recommendations", 0),
                "name": data.get("name", ""),
                "subtitle": data.get("subtitle", ""),
                "raw": data,
            }
    except Exception:
        # Microservice unavailable, attempt fallback
        pass

    # Method 2: Direct contact sync via stored account tokens
    tokens = _load_direct_tokens(limit=5)
    for token in tokens:
        try:
            res = _check_direct_contact_sync(m10, token)
            if res.get("status") == "AUTH_ERROR":
                continue
            return res
        except Exception:
            continue

    return {
        "status": "ERROR",
        "mobile": m10,
        "error": "Zomato checker service offline and no valid account token found",
    }


# ------------------------------------------------------------
# CLI Runner
# ------------------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python zomato_check.py <10-digit> [more numbers...]")
        print("       python zomato_check.py numbers.txt")
        sys.exit(1)

    args = sys.argv[1:]
    numbers: List[str] = []

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
        m10 = normalize_mobile(num)
        print(f"[{i}/{total}] {m10} ... ", end="", flush=True)
        res = check_zomato(m10)
        print(res.get("status", "UNKNOWN"))
        pretty_print(res)
        if i < total:
            time.sleep(BULK_DELAY)


if __name__ == "__main__":
    main()
