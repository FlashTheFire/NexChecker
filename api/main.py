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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NEXBOT_ROOT = PROJECT_ROOT / "NexBot"
for p in (str(PROJECT_ROOT), str(NEXBOT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ------------------------------------------------------------
# Import Checker Functions
# ------------------------------------------------------------
try:
    from zomato_check import check_zomato
except Exception:
    check_zomato = None

try:
    from flipkart_check import check_flipkart
except Exception:
    check_flipkart = None

try:
    from bigbasket_check import check_bigbasket
except Exception:
    check_bigbasket = None

try:
    from myntra_check import check_myntra
except Exception:
    check_myntra = None

try:
    from foja_client import FojaClient, clean_phone
    _foja = FojaClient()
except Exception:
    _foja = None
    clean_phone = None


# ------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------
class PhoneCheckRequest(BaseModel):
    target_phone: str = Field(..., description="10-digit Indian phone number")
    platform: Optional[str] = Field("zomato", description="Platform key: zomato | flipkart | bigbasket | myntra | meesho | all")
    checker_phone: Optional[str] = Field(None, description="Optional caller phone context")


class BatchCheckRequest(BaseModel):
    phones: List[str] = Field(..., description="List of 10-digit Indian phone numbers")
    platform: Optional[str] = Field("zomato", description="Platform key: zomato | flipkart | bigbasket | myntra | meesho")


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
# Dispatcher Helper
# ------------------------------------------------------------
async def _execute_check(platform: str, phone: str) -> Dict[str, Any]:
    pkey = platform.lower().strip()
    clean = "".join(c for c in str(phone) if c.isdigit())
    if len(clean) >= 10:
        clean = clean[-10:]

    if pkey == "zomato":
        if check_zomato:
            return await asyncio.to_thread(check_zomato, clean)
        return {"status": "ERROR", "error": "Zomato checker engine unavailable"}

    elif pkey == "flipkart":
        if check_flipkart:
            return await asyncio.to_thread(check_flipkart, clean)
        return {"status": "ERROR", "error": "Flipkart checker engine unavailable"}

    elif pkey == "bigbasket":
        if check_bigbasket:
            return await asyncio.to_thread(check_bigbasket, clean)
        return {"status": "ERROR", "error": "BigBasket checker engine unavailable"}

    elif pkey == "myntra":
        if check_myntra:
            return await asyncio.to_thread(check_myntra, clean)
        return {"status": "ERROR", "error": "Myntra checker engine unavailable"}

    elif pkey == "meesho":
        if _foja:
            res = await asyncio.to_thread(_foja.check_number, clean)
            is_reg = bool(res.get("registered") or res.get("status") == "registered")
            return {
                "status": "REGISTERED" if is_reg else "NOT_REGISTERED",
                "registered": is_reg,
                "mobile": clean,
                "raw": res,
            }
        return {"status": "ERROR", "error": "Meesho checker engine unavailable"}

    elif pkey == "all":
        results = {}
        for p in ("zomato", "flipkart", "bigbasket", "myntra", "meesho"):
            results[p] = await _execute_check(p, clean)
        return {"status": "SUCCESS", "mobile": clean, "platforms": results}

    else:
        return {"status": "ERROR", "error": f"Unknown platform: '{platform}'"}


# ------------------------------------------------------------
# Core Endpoints
# ------------------------------------------------------------
@app.get("/api/health")
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker & Cloudflare Tunnel."""
    return {
        "status": "healthy",
        "service": "NexChecker",
        "timestamp": int(time.time()),
        "engines": {
            "zomato": check_zomato is not None,
            "flipkart": check_flipkart is not None,
            "bigbasket": check_bigbasket is not None,
            "myntra": check_myntra is not None,
            "meesho": _foja is not None,
        },
    }


@app.get("/api/platforms")
async def list_platforms():
    """List all supported platforms with metadata."""
    return {
        "platforms": [
            {"key": "zomato", "label": "Zomato", "icon": "🍽", "status": "active", "service_code": "zo"},
            {"key": "flipkart", "label": "Flipkart", "icon": "🛍", "status": "active", "service_code": "xt"},
            {"key": "bigbasket", "label": "BigBasket", "icon": "🛒", "status": "active", "service_code": "bb"},
            {"key": "myntra", "label": "Myntra", "icon": "📦", "status": "active", "service_code": "nl"},
            {"key": "meesho", "label": "Meesho", "icon": "⚡", "status": "active", "service_code": "hp"},
        ]
    }


@app.post("/api/checker/phone")
@app.post("/api/check/phone")
async def check_single_phone(req: PhoneCheckRequest):
    """Check a single mobile number on a target platform or all platforms."""
    clean = "".join(c for c in req.target_phone if c.isdigit())
    if len(clean) >= 10:
        clean = clean[-10:]
    if len(clean) != 10:
        raise HTTPException(status_code=400, detail="Invalid 10-digit mobile number")

    result = await _execute_check(req.platform or "zomato", clean)
    return {
        "success": result.get("status") in ("REGISTERED", "NOT_REGISTERED", "SUCCESS"),
        "phone": clean,
        "platform": req.platform,
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
# WebApp Static Files
# ------------------------------------------------------------
webapp_dir = PROJECT_ROOT / "webapp"
if webapp_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(webapp_dir)), name="assets")

    @app.get("/")
    async def serve_index():
        index_file = webapp_dir / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
        return {"message": "NexChecker Universal API & Webapp Active"}
