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
    try:
        from zomato_check import check_zomato
    except Exception:
        check_zomato = None

try:
    from checkers.flipkart_check import check_flipkart
except Exception:
    try:
        from flipkart_check import check_flipkart
    except Exception:
        check_flipkart = None

try:
    from checkers.bigbasket_check import check_bigbasket
except Exception:
    try:
        from bigbasket_check import check_bigbasket
    except Exception:
        check_bigbasket = None

try:
    from checkers.myntra_check import check_myntra
except Exception:
    try:
        from myntra_check import check_myntra
    except Exception:
        check_myntra = None

try:
    from checkers.meesho_check import check_meesho
except Exception:
    try:
        from meesho_check import check_meesho
    except Exception:
        check_meesho = None

try:
    from checkers.amazon_check import check_amazon
except Exception:
    try:
        from amazon_check import check_amazon
    except Exception:
        check_amazon = None

try:
    from checkers.swiggy_check import check_swiggy
except Exception:
    try:
        from swiggy_check import check_swiggy
    except Exception:
        check_swiggy = None

try:
    from checkers.zepto_check import check_zepto
except Exception:
    try:
        from zepto_check import check_zepto
    except Exception:
        check_zepto = None


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

# In-memory real-time counters (resets on restart; extend with Redis if needed)
_stats: Dict[str, Any] = {
    "total_checks": 0,
    "latency_samples": [],  # last 100 latency readings in ms
}


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

    # Record real latency + increment check counter
    elapsed_ms = (time.perf_counter() - t_start) * 1000
    _stats["total_checks"] += 1
    samples = _stats["latency_samples"]
    samples.append(elapsed_ms)
    if len(samples) > 100:
        _stats["latency_samples"] = samples[-100:]

    return result


# ------------------------------------------------------------
# Core Endpoints
# ------------------------------------------------------------
@app.get("/api/health")
@app.get("/health")
async def health_check():
    """Health check endpoint — returns real check count and latency stats."""
    samples = _stats["latency_samples"]
    avg_ms = round(sum(samples) / len(samples), 1) if samples else None
    return {
        "status": "healthy",
        "service": "NexChecker",
        "version": "3.0.0",
        "timestamp": int(time.time()),
        "total_checks": _stats["total_checks"],
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
async def check_single_phone(req: PhoneCheckRequest):
    """Check a single mobile number on a target platform or all platforms."""
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
    return {
        "success": result.get("status") in ("REGISTERED", "NOT_REGISTERED", "SUCCESS"),
        "phone": clean,
        "platform": platform,
        "registered": result.get("registered", False),
        "fresh": result.get("fresh", not result.get("registered", False)),
        **result,
    }


@app.post("/api/checker/batch")
@app.post("/api/check/batch")
async def check_batch_phones(req: BatchCheckRequest):
    """Check a list of phone numbers concurrently."""
    pkey = req.platform or "zomato"
    phones = req.phones[:50]  # Cap at 50 per request

    tasks = [_execute_check(pkey, p) for p in phones]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    formatted = {}
    for p, res in zip(phones, results_list):
        clean = "".join(c for c in p if c.isdigit())[-10:]
        if isinstance(res, Exception):
            formatted[clean] = {"status": "ERROR", "error": str(res)}
        else:
            formatted[clean] = res

    return {
        "success": True,
        "platform": pkey,
        "total": len(phones),
        "results": formatted,
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
            from bot import bot as tele_bot
        except ImportError:
            from NexBot.bot import bot as tele_bot

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
