#!/usr/bin/env python3
"""
Meesho Silent Registration Checker (PriceTrackerPro / Foja Engine)
=================================================================
Ultra-fast, authoritative Meesho registration checking without sending
any OTP or SMS to the target number.

Usage:
  python meesho_check.py 9365647902
  python meesho_check.py 9365647902 9027936246 6000000000
  python meesho_check.py --raw 9365647902
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

try:
    from checkers.foja_client import FojaClient, clean_phone
except ImportError:
    from foja_client import FojaClient, clean_phone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BULK_DELAY = 0.5


def check_meesho(mobile: str) -> dict[str, Any]:
    norm = clean_phone(mobile)
    if len(norm) != 10 or norm[0] not in "6789":
        return {
            "status": "ERROR",
            "mobile": norm,
            "error": "invalid 10-digit Indian mobile",
            "raw": None,
        }

    try:
        client = FojaClient()
        res = client.check_number(norm)
        status = "REGISTERED" if res.registered else "NOT_REGISTERED"
        return {
            "status": status,
            "mobile": norm,
            "registered": res.registered,
            "fresh": res.fresh,
            "raw": res.raw,
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "mobile": norm,
            "error": f"{type(e).__name__}: {e}",
            "raw": None,
        }


def pretty_print(result: dict) -> None:
    status = result.get("status")
    mobile = result.get("mobile", "")

    if status == "REGISTERED":
        print(
            f"""❰ ✅ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗙𝗢𝗨𝗡𝗗 🎯 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✓ sᴛᴀᴛᴜs ʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🛒 ᴍᴇᴇsʜᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
🎯 Active Meesho account detected."""
        )
    elif status == "NOT_REGISTERED":
        print(
            f"""❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 🛒 ᴍᴇᴇsʜᴏ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
✅ No active Meesho account on this number (FRESH)."""
        )
    else:
        print(f"Result: {result}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Meesho silent registration checker")
    ap.add_argument("mobiles", nargs="+", help="10-digit mobile number(s)")
    ap.add_argument("--raw", action="store_true", help="always print full result dict")
    args = ap.parse_args()

    total = len(args.mobiles)
    for i, raw in enumerate(args.mobiles, 1):
        mobile = clean_phone(raw)
        print(f"[{i}/{total}] {mobile} ... ", end="", flush=True)
        result = check_meesho(mobile)
        print(result.get("status", "ERROR"))
        if args.raw or result.get("status") not in ("REGISTERED", "NOT_REGISTERED"):
            print(f"Result: {result}")
        else:
            pretty_print(result)
        if i < total:
            time.sleep(BULK_DELAY)


if __name__ == "__main__":
    main()
