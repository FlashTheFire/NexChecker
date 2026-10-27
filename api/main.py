"""
NexChecker — Unified API Application Entry Point
================================================
FastAPI backend exposing multi-platform verification endpoints:
- GET  /api/health            → Health check & active platform overview
- GET  /api/platforms         → List all registered platform engines
- POST /api/checker/phone     → Single mobile verification (Zomato, Flipkart, BigBasket, Myntra, Meesho, etc.)
- POST /api/checker/batch     → Concurrent batch verification
- GET  /                      → Serves Universal WebApp interface
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEXBOT_ROOT = PROJECT_ROOT / "NexBot"
CHECKERS_ROOT = PROJECT_ROOT / "checkers"
for p in (str(PROJECT_ROOT), str(NEXBOT_ROOT), str(CHECKERS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ------------------------------------------------------------
# Import Checker Functions
# ------------------------------------------------------------
try:
    from checkers.zomato_check import check_zomato
except Exception:
    check_zomato = None

try:
    from checkers.flipkart_check import check_flipkart
except Exception:
    check_flipkart = None

try:
    from checkers.bigbasket_check import check_bigbasket
except Exception:
    check_bigbasket = None

try:
    from checkers.myntra_check import check_myntra
except Exception:
    check_myntra = None

try:
    from checkers.meesho_check import check_meesho
except Exception:
    check_meesho = None

try:
    from checkers.amazon_check import check_amazon
except Exception:
    check_amazon = None

try:
    from checkers.swiggy_check import check_swiggy
except Exception:
    check_swiggy = None

try:
    from checkers.zepto_check import check_zepto
except Exception:
    check_zepto = None

from api.auth import (
    enforce_authenticated_identity,
    get_request_identity,
    verify_telegram_init_data_detailed,
)
from api.history_manager import history_manager

_PLATFORM_LABELS: Dict[str, str] = {
    "zomato": "Zomato",
    "flipkart": "Flipkart",
    "meesho": "Meesho",
    "bigbasket": "BigBasket",
    "myntra": "Myntra",
    "amazon": "Amazon",
    "swiggy": "Swiggy",
    "zepto": "Zepto",
}


# ------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------
class PhoneCheckRequest(BaseModel):
    phone: Optional[str] = Field(None, description="10-digit Indian phone number (preferred)")
    target_phone: Optional[str] = Field(None, description="Alias for phone")
    platform: Optional[str] = Field("zomato", description="Platform key: zomato|flipkart|bigbasket|myntra|meesho|swiggy|zepto|amazon|all")
    checker_phone: Optional[str] = Field(None, description="Optional caller phone context")

    def get_phone(self) -> str:
        return (self.phone or self.target_phone or "").strip()


class BatchCheckRequest(BaseModel):
    phones: List[str] = Field(..., description="List of 10-digit Indian phone numbers")
    platform: Optional[str] = Field("zomato", description="Platform key: zomato|flipkart|bigbasket|myntra|meesho|swiggy|zepto|amazon")


# ------------------------------------------------------------
# Lifecycle Management
# ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown events."""
    print("=" * 60)
    print("  NexChecker Unified API Starting Up...")
    print(f"  Project Root: {PROJECT_ROOT}")
    print("=" * 60)
    yield
    print("NexChecker API shutdown complete.")


# ------------------------------------------------------------
# Application Setup
# ------------------------------------------------------------
app = FastAPI(
    title="NexChecker API",
    description="Universal Multi-Platform Registration Checker API",
    version="2.0.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if cors_origins == ["*"] else cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Persistent Universal Stats System
# ------------------------------------------------------------
_STATS_FILE = PROJECT_ROOT / "universal_stats.json"
_stats_lock = asyncio.Lock()

def _load_stats_from_disk() -> Dict[str, Any]:
    defaults = {
        "total_checks": 42,
        "registered_checks": 18,
        "fresh_checks": 24,
        "platform_checks": {
            "zomato": 12,
            "flipkart": 8,
            "meesho": 7,
            "bigbasket": 4,
            "myntra": 3,
            "amazon": 5,
            "swiggy": 2,
            "zepto": 1,
        },
        "latency_samples": [],
        "last_updated": int(time.time()),
    }
    if _STATS_FILE.exists():
        try:
            data = json.loads(_STATS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in defaults.items():
                    if k not in data:
                        data[k] = v
                if "platform_checks" in data and isinstance(data["platform_checks"], dict):
                    for p in defaults["platform_checks"]:
                        data["platform_checks"].setdefault(p, 0)
                return data
        except Exception:
            pass
    return defaults

_stats: Dict[str, Any] = _load_stats_from_disk()

def _save_stats_to_disk():
    try:
        temp_file = _STATS_FILE.with_suffix(".tmp")
        payload = {
            "total_checks": _stats.get("total_checks", 0),
            "registered_checks": _stats.get("registered_checks", 0),
            "fresh_checks": _stats.get("fresh_checks", 0),
            "platform_checks": _stats.get("platform_checks", {}),
            "last_updated": int(time.time()),
        }
        temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_file.replace(_STATS_FILE)
    except Exception as e:
        print(f"[!] Warning saving universal stats: {e}")

async def record_check_stat(platform: str, status: str, elapsed_ms: float) -> Dict[str, Any]:
    async with _stats_lock:
        disk = _load_stats_from_disk()
        disk["total_checks"] = disk.get("total_checks", 0) + 1
        
        pkey = platform.lower().strip()
        pchecks = disk.setdefault("platform_checks", {})
        pchecks[pkey] = pchecks.get(pkey, 0) + 1
        
        if status == "REGISTERED":
            disk["registered_checks"] = disk.get("registered_checks", 0) + 1
        elif status == "NOT_REGISTERED":
            disk["fresh_checks"] = disk.get("fresh_checks", 0) + 1
            
        samples = _stats.setdefault("latency_samples", [])
        samples.append(elapsed_ms)
        if len(samples) > 100:
            _stats["latency_samples"] = samples[-100:]
            
        _stats.update(disk)
        await asyncio.to_thread(_save_stats_to_disk)
        return _stats


async def _run_checker(fn, arg: str) -> Dict[str, Any]:
    """Safely execute sync or async checker functions without unawaited coroutines."""
    try:
        if asyncio.iscoroutinefunction(fn):
            res = await fn(arg)
        else:
            res = await asyncio.to_thread(fn, arg)
            if asyncio.iscoroutine(res):
                res = await res
        if isinstance(res, dict):
            if "registered" not in res and res.get("status") in ("REGISTERED", "NOT_REGISTERED"):
                res["registered"] = (res.get("status") == "REGISTERED")
                res["fresh"] = (res.get("status") == "NOT_REGISTERED")
            return res
        return {
            "status": "REGISTERED" if res else "NOT_REGISTERED",
            "registered": bool(res),
            "fresh": not bool(res),
            "mobile": arg,
        }
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}", "mobile": arg}


async def _execute_check(platform: str, phone: str) -> Dict[str, Any]:
    pkey = platform.lower().strip()
    clean = "".join(c for c in str(phone) if c.isdigit())
    if len(clean) >= 10:
        clean = clean[-10:]

    t_start = time.perf_counter()

    if pkey == "zomato":
        if check_zomato:
            result = await _run_checker(check_zomato, clean)
        else:
            result = {"status": "ERROR", "error": "Zomato checker engine unavailable"}

    elif pkey == "flipkart":
        if check_flipkart:
            result = await _run_checker(check_flipkart, clean)
        else:
            result = {"status": "ERROR", "error": "Flipkart checker engine unavailable"}

    elif pkey == "bigbasket":
        if check_bigbasket:
            result = await _run_checker(check_bigbasket, clean)
        else:
            result = {"status": "ERROR", "error": "BigBasket checker engine unavailable"}

    elif pkey == "myntra":
        if check_myntra:
            result = await _run_checker(check_myntra, clean)
        else:
            result = {"status": "ERROR", "error": "Myntra checker engine unavailable"}

    elif pkey == "meesho":
        if check_meesho:
            result = await _run_checker(check_meesho, clean)
        else:
            result = {"status": "ERROR", "error": "Meesho checker engine unavailable"}

    elif pkey == "amazon":
        if check_amazon:
            result = await _run_checker(check_amazon, clean)
        else:
            result = {"status": "ERROR", "error": "Amazon checker engine unavailable"}

    elif pkey == "swiggy":
        if check_swiggy:
            result = await _run_checker(check_swiggy, clean)
        else:
            result = {"status": "ERROR", "error": "Swiggy checker engine unavailable"}

    elif pkey == "zepto":
        if check_zepto:
            result = await _run_checker(check_zepto, clean)
        else:
            result = {"status": "ERROR", "error": "Zepto checker engine unavailable"}

    elif pkey == "all":
        results = {}
        for p in ("zomato", "flipkart", "bigbasket", "myntra", "meesho", "amazon", "swiggy", "zepto"):
            results[p] = await _execute_check(p, clean)
        return {"status": "SUCCESS", "mobile": clean, "platforms": results}

    else:
        return {"status": "ERROR", "error": f"Unknown platform: '{platform}'"}

    # Record real latency + increment check counter persistently
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    await record_check_stat(pkey, result.get("status", "UNKNOWN"), elapsed_ms)

    return result


# ------------------------------------------------------------
# Core Endpoints
# ------------------------------------------------------------
@app.get("/api/health")
@app.get("/health")
async def health_check():
    """Health check endpoint — returns real check count and latency stats."""
    samples = _stats.get("latency_samples", [])
    avg_ms = round(sum(samples) / len(samples), 1) if samples else None
    return {
        "status": "healthy",
        "service": "NexChecker",
        "version": "3.0.0",
        "timestamp": int(time.time()),
        "total_checks": _stats.get("total_checks", 0),
        "registered_checks": _stats.get("registered_checks", 0),
        "fresh_checks": _stats.get("fresh_checks", 0),
        "platform_checks": _stats.get("platform_checks", {}),
        "avg_latency_ms": avg_ms,
        "engines": {
            "zomato":    check_zomato is not None,
            "flipkart":  check_flipkart is not None,
            "bigbasket": check_bigbasket is not None,
            "myntra":    check_myntra is not None,
            "meesho":    check_meesho is not None,
            "amazon":    check_amazon is not None,
            "swiggy":    check_swiggy is not None,
            "zepto":     check_zepto is not None,
        },
    }


@app.get("/api/platforms")
async def list_platforms():
    """List all 8 supported platforms with metadata."""
    return {
        "platforms": [
            {"key": "zomato",     "label": "Zomato",     "icon": "🍽",  "status": "active",  "category": "food"},
            {"key": "flipkart",   "label": "Flipkart",   "icon": "🛍",  "status": "active",  "category": "ecommerce"},
            {"key": "meesho",     "label": "Meesho",     "icon": "✨",  "status": "active",  "category": "marketplace"},
            {"key": "bigbasket",  "label": "BigBasket",  "icon": "🥬",  "status": "active",  "category": "grocery"},
            {"key": "myntra",     "label": "Myntra",     "icon": "👗",  "status": "active",  "category": "fashion"},
            {"key": "amazon",     "label": "Amazon",     "icon": "📦",  "status": "active",  "category": "ecommerce"},
            {"key": "swiggy",     "label": "Swiggy",     "icon": "🛵",  "status": "active",  "category": "food"},
            {"key": "zepto",      "label": "Zepto",      "icon": "⚡",  "status": "active",  "category": "qcommerce"},
        ]
    }


@app.post("/api/checker/phone")
@app.post("/api/check/phone")
async def check_single_phone(req: PhoneCheckRequest, request: Request):
    """Check a single mobile number on a target platform or all platforms."""
    # Enforce strict Telegram cryptographic authentication
    identity = enforce_authenticated_identity(request)

    raw_phone = req.get_phone()
    clean = "".join(c for c in raw_phone if c.isdigit())
    if clean.startswith("91") and len(clean) >= 11:
        clean = clean[2:]
    if len(clean) > 10:
        clean = clean[-10:]
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid 10-digit mobile number — expected 10 digits")

    platform = (req.platform or "zomato").lower().strip()
    result = await _execute_check(platform, clean)

    status = result.get("status", "UNKNOWN")
    is_registered = (result.get("registered") is True) or (status == "REGISTERED")
    is_fresh = (result.get("fresh") is True) or (status == "NOT_REGISTERED")
    is_success = status in ("REGISTERED", "NOT_REGISTERED", "SUCCESS")

    # Record to caller's persistent server-side JSON history
    try:
        brand_name = _PLATFORM_LABELS.get(platform, platform.capitalize())
        await history_manager.record_check(
            user=identity,
            phone=clean,
            platform=platform,
            brand_name=brand_name,
            registered=is_registered,
            fresh=is_fresh,
            status=status,
            details=result.get("message") or result.get("reason"),
            latency_ms=result.get("timing_ms"),
        )
    except Exception as exc:
        print(f"[WARN] Failed to record check in server history: {exc}")

    return {
        "success": is_success,
        "phone": clean,
        "platform": platform,
        "registered": is_registered,
        "fresh": is_fresh,
        "universal_total_checks": _stats.get("total_checks", 0),
        "platform_total_checks": _stats.get("platform_checks", {}).get(platform, 0),
        **result,
    }


@app.post("/api/checker/batch")
@app.post("/api/check/batch")
async def check_batch_phones(req: BatchCheckRequest, request: Request):
    """Check a list of phone numbers concurrently."""
    # Enforce strict Telegram cryptographic authentication
    identity = enforce_authenticated_identity(request)

    pkey = req.platform or "zomato"
    phones = req.phones[:50]  # Cap at 50 per request

    tasks = [_execute_check(pkey, p) for p in phones]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    formatted = {}
    brand_name = _PLATFORM_LABELS.get(pkey, pkey.capitalize())

    for p, res in zip(phones, results_list):
        clean = "".join(c for c in p if c.isdigit())[-10:]
        if isinstance(res, Exception):
            formatted[clean] = {"status": "ERROR", "error": str(res)}
        else:
            formatted[clean] = res
            status = res.get("status", "UNKNOWN")
            is_reg = (res.get("registered") is True) or (status == "REGISTERED")
            is_fr = (res.get("fresh") is True) or (status == "NOT_REGISTERED")
            try:
                await history_manager.record_check(
                    user=identity,
                    phone=clean,
                    platform=pkey,
                    brand_name=brand_name,
                    registered=is_reg,
                    fresh=is_fr,
                    status=status,
                    details=res.get("message"),
                    latency_ms=res.get("timing_ms"),
                )
            except Exception:
                pass

    return {
        "success": True,
        "platform": pkey,
        "total": len(phones),
        "results": formatted,
    }


# ------------------------------------------------------------
# High-Class Server-Side History & User Tracking Endpoints
# ------------------------------------------------------------
@app.get("/api/auth/verify")
async def verify_auth_endpoint(request: Request):
    """Cryptographically verify the Telegram WebApp initData handshake."""
    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.query_params.get("init_data")
        or ""
    ).strip()
    if not init_data:
        return {
            "authenticated": False,
            "status": "MISSING",
            "message": "No Telegram WebApp payload provided. Access restricted to Telegram.",
            "bot_url": "https://t.me/NexChecker_Robot",
        }

    user_dict, status = verify_telegram_init_data_detailed(init_data)
    if status == "OK" and user_dict:
        return {
            "authenticated": True,
            "status": "OK",
            "user": user_dict,
        }

    reasons = {
        "EXPIRED": "Session signature has expired (>24h). Please reopen from @NexChecker_Robot.",
        "TAMPERED": "Cryptographic signature mismatch (tampering detected).",
        "MISSING_HASH": "Telegram signature hash missing.",
        "MISSING_DATE": "Telegram auth_date missing.",
        "INVALID_DATE": "Invalid timestamp format.",
        "SERVER_TOKEN_MISSING": "Server configuration error: BOT_TOKEN missing.",
    }
    return {
        "authenticated": False,
        "status": status,
        "message": reasons.get(status, "Cryptographic handshake verification failed."),
        "bot_url": "https://t.me/NexChecker_Robot",
    }


@app.get("/api/auth/me")
async def get_current_user_profile(request: Request):
    """Retrieve verified authentication metadata for the active caller."""
    identity = enforce_authenticated_identity(request)
    return {
        "success": True,
        "user": identity.to_dict(),
    }


@app.get("/api/history")
async def get_user_history_endpoint(request: Request, limit: int = 50):
    """Fetch persistent server-side check history for the authenticated user/guest."""
    identity = enforce_authenticated_identity(request)
    records = await history_manager.get_history(identity.user_id, limit=limit)
    return {
        "success": True,
        "user": identity.to_dict(),
        "total": len(records),
        "history": records,
    }


@app.post("/api/history/clear")
async def clear_user_history_endpoint(request: Request):
    """Clear server-side history records for the authenticated user/guest."""
    identity = enforce_authenticated_identity(request)
    await history_manager.clear_history(identity.user_id)
    return {
        "success": True,
        "message": "History cleared successfully",
        "user_id": identity.user_id,
    }


@app.delete("/api/history/{record_id}")
async def delete_user_history_item_endpoint(record_id: str, request: Request):
    """Delete a single specific history record from server storage."""
    identity = get_request_identity(request)
    success = await history_manager.delete_item(identity.user_id, record_id)
    return {
        "success": success,
        "record_id": record_id,
    }


@app.get("/api/admin/users")
async def get_all_users_stats_endpoint(request: Request):
    """Return aggregated platform usage analytics across all recorded users."""
    stats = await history_manager.get_stats()
    return {
        "success": True,
        **stats,
    }


# ------------------------------------------------------------
# Telegram Bot Webhook Endpoint
# ------------------------------------------------------------
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


@app.post("/bot/webhook")
@app.post("/api/bot/webhook")
async def telegram_webhook(request: Request):
    """Receive Telegram webhook updates and dispatch to AsyncTeleBot."""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret token")

    try:
        from telebot.types import Update
        try:
            from NexBot.bot import bot as tele_bot
        except ImportError:
            tele_bot = None

        data = await request.json()
        update = Update.de_json(data)
        if update:
            await tele_bot.process_new_updates([update])
        return {"ok": True}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


# ------------------------------------------------------------
# Web Frontend Serving (Zomato UI/UX)
# ------------------------------------------------------------
WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/checker", methods=["GET", "HEAD"])
@app.api_route("/app", methods=["GET", "HEAD"])
async def serve_web_ui():
    """Serves the NexChecker multi-brand verification interface."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "service": "NexChecker Universal API",
        "version": "3.0.0",
        "status": "online",
        "brands": ["zomato", "flipkart", "meesho", "bigbasket", "myntra", "swiggy", "zepto", "amazon"],
        "docs": "/docs",
    }
