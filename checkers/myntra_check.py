#!/usr/bin/env python3
"""
Myntra Silent Registration Checker (ProMyntra Engine)
===================================================
Ultra-fast, authoritative Myntra registration checking without sending
any OTP or SMS to the target number.

Usage:
  python myntra_check.py 9027936246
  python myntra_check.py 9027936246 9999999999 8891523001
  python myntra_check.py --raw 9027936246
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NEXBOT_ROOT = _PROJECT_ROOT / "NexBot"
for _p in (str(_PROJECT_ROOT), str(_NEXBOT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from core.myntra_api import (
        MyntraClient,
        MyntraChecker,
        myntra_checker,
        clean_phone,
    )
except ImportError:
    try:
        from NexBot.core.myntra_api import (
            MyntraClient,
            MyntraChecker,
            myntra_checker,
            clean_phone,
        )
    except ImportError:
        from myntra_api import (
            MyntraClient,
            MyntraChecker,
            myntra_checker,
            clean_phone,
        )

# Backward compatibility alias
normalize_mobile = clean_phone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BULK_DELAY = 0.5


def check_myntra(mobile: str) -> dict[str, Any]:
    """Check a single Indian mobile number against Myntra."""
    norm = clean_phone(mobile)
    if len(norm) != 10 or norm[0] not in "6789":
        return {
            "status": "ERROR",
            "mobile": norm,
            "error": "invalid 10-digit Indian mobile",
            "raw": None,
        }

    try:
        client = MyntraClient()
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


async def check_myntra_async(mobile: str) -> dict[str, Any]:
    """Asynchronous check of a single mobile number against Myntra."""
    norm = clean_phone(mobile)
    if len(norm) != 10 or norm[0] not in "6789":
        return {
            "status": "ERROR",
            "mobile": norm,
            "error": "invalid 10-digit Indian mobile",
            "raw": None,
        }

    try:
        client = MyntraClient()
        res = await client.check_number_async(norm)
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
🎯 ᴘʟᴀᴛғᴏʀᴍ 📦 ᴍʏɴᴛʀᴀ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
🎯 Active Myntra account detected."""
        )
    elif status == "NOT_REGISTERED":
        print(
            f"""❰ ❌ 𝗡𝗢𝗧 𝗥𝗘𝗚𝗜𝗦𝗧𝗘𝗥𝗘𝗗 ❱
┏━━━━━━━━━━━━━━━━━━━━┓
✗ sᴛᴀᴛᴜs ᴜɴʀᴇɢɪsᴛᴇʀᴇᴅ
🎯 ᴘʟᴀᴛғᴏʀᴍ 📦 ᴍʏɴᴛʀᴀ
📱 ɴᴜᴍʙᴇʀ {mobile}
┗━━━━━━━━━━━━━━━━━━━━┛
✅ No active Myntra account on this number (FRESH)."""
        )
    else:
        print(f"Result: {result}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Myntra silent registration checker")
    ap.add_argument("mobiles", nargs="*", help="10-digit mobile number(s)")
    ap.add_argument("-f", "--file", help="file containing numbers (one per line)")
    ap.add_argument("--raw", action="store_true", help="always print full result dict")
    ap.add_argument("--json", action="store_true", help="print JSON output")
    args = ap.parse_args()

    numbers: list[str] = []
    if args.file:
        numbers = [
            ln.strip()
            for ln in Path(args.file).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    numbers.extend(args.mobiles)

    if not numbers:
        ap.print_help()
        print("\nExamples:")
        print("  python myntra_check.py 9027936246")
        print("  python myntra_check.py 9027936246 9999999999")
        sys.exit(1)

    total = len(numbers)
    json_results = []
    for i, raw in enumerate(numbers, 1):
        mobile = clean_phone(raw)
        if not args.json:
            print(f"[{i}/{total}] {mobile} ... ", end="", flush=True)
        result = check_myntra(mobile)
        if args.json:
            json_results.append(result)
        else:
            print(result.get("status", "ERROR"))
            if args.raw or result.get("status") not in ("REGISTERED", "NOT_REGISTERED"):
                print(f"Result: {result}")
            else:
                pretty_print(result)
            if i < total:
                time.sleep(BULK_DELAY)

    if args.json:
        import json
        print(json.dumps(json_results, indent=2))


if __name__ == "__main__":
    main()
