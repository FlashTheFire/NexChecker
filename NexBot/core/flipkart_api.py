"""NexBot — Flipkart checker API wrapper.

Wraps flipkart_check.py into the unified Checker interface:
  - check_number(mobile) → {"status": "REGISTERED"|"NOT_REGISTERED"|"UNKNOWN"|"ERROR", ...}
  - startup()  → marks ready (HTTP endpoints active)
  - shutdown() → marks unready
  - is_ready   → True

No Playwright warmup needed — pure HTTP endpoints (rome.api.flipkart.com).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Resolve flipkart_check.py relative to the NexChecker root (parent of NexBot)
_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent.parent


class FlipkartChecker:
    """Manages Flipkart registration checks.

    Delegates to check_flipkart() in flipkart_check.py via asyncio.to_thread
    to ensure non-blocking execution inside the asyncio event loop.
    """

    def __init__(self) -> None:
        self._lock  = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Flipkart uses direct HTTP endpoints — no browser or state file required."""
        self._ready = True
        logger.info("[Flipkart] Ready — HTTP endpoint registered (rome.api.flipkart.com)")

    async def shutdown(self) -> None:
        """No-op — no browser context to close."""
        self._ready = False

    # ── Check ─────────────────────────────────────────────────────────────────

    async def check_number(self, mobile: str) -> Dict[str, Any]:
        """Check a single mobile number against Flipkart.

        Returns a dict with at minimum:
          {"status": "REGISTERED" | "NOT_REGISTERED" | "UNKNOWN" | "ERROR"}
        """
        async with self._lock:
            try:
                import sys
                root_str = str(_NEXCHECKER_DIR)
                if root_str not in sys.path:
                    sys.path.insert(0, root_str)
                from flipkart_check import check_flipkart  # type: ignore

                result = await asyncio.to_thread(check_flipkart, mobile)
                return result
            except Exception as exc:
                logger.error("[Flipkart] check_number error: %s", exc)
                return {"status": "ERROR", "mobile": mobile, "error": str(exc)}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Module singleton ──────────────────────────────────────────────────────────
flipkart_checker = FlipkartChecker()
