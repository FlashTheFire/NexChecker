"""NexBot — Zomato checker API wrapper.

Wraps zomato_check.py into the unified Checker interface:
  - check_number(mobile) → {"status": "REGISTERED"|"NOT_REGISTERED"|"UNKNOWN"|"ERROR", ...}
  - startup()  → marks ready
  - shutdown() → marks unready
  - is_ready   → True

No Playwright warmup needed — pure HTTP contact sync / checker microservice.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Resolve zomato_check.py relative to the NexChecker root (parent of NexBot)
_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent.parent


class ZomatoChecker:
    """Manages Zomato registration checks.

    Delegates to check_zomato() in zomato_check.py via asyncio.to_thread
    to ensure non-blocking execution inside the asyncio event loop.
    """

    def __init__(self) -> None:
        self._lock  = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Zomato uses direct HTTP / contact-sync endpoints — no browser required."""
        self._ready = True
        logger.info("[Zomato] Ready — Zomato registration checker initialized")

    async def shutdown(self) -> None:
        """No-op — no browser context to close."""
        self._ready = False

    # ── Check ─────────────────────────────────────────────────────────────────

    async def check_number(self, mobile: str) -> Dict[str, Any]:
        """Check a single mobile number against Zomato.

        Returns a dict with at minimum:
          {"status": "REGISTERED" | "NOT_REGISTERED" | "UNKNOWN" | "ERROR"}
        """
        async with self._lock:
            try:
                import sys
                root_str = str(_NEXCHECKER_DIR)
                if root_str not in sys.path:
                    sys.path.insert(0, root_str)
                from zomato_check import check_zomato  # type: ignore

                result = await asyncio.to_thread(check_zomato, mobile)
                return result
            except Exception as exc:
                logger.error("[Zomato] check_number error: %s", exc)
                return {"status": "ERROR", "mobile": mobile, "error": str(exc)}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Module singleton ──────────────────────────────────────────────────────────
zomato_checker = ZomatoChecker()
