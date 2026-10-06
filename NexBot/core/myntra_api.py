"""NexBot — Myntra checker API wrapper.

Wraps myntra_check.py into the unified Checker interface:
  - check_number(mobile) → {"status": "REGISTERED"|"NOT_REGISTERED"|"UNKNOWN"|"ERROR", ...}
  - startup()  → starts Chrome context via myntra_check.py
  - shutdown() → closes Chrome context and saves state
  - is_ready   → True when Chrome page is active
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Resolve myntra_check.py relative to the NexChecker root (parent of NexBot)
_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent.parent


class MyntraChecker:
    """Manages Myntra registration checks.

    Delegates to check_myntra() in myntra_check.py.
    """

    def __init__(self) -> None:
        self._lock  = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Launch real Chrome context via myntra_check."""
        try:
            import sys
            root_str = str(_NEXCHECKER_DIR)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            from utils.config import PROXY
            import myntra_check

            is_linux = sys.platform.startswith("linux")
            await myntra_check.myntra_checker.startup(headless=is_linux, proxy=PROXY)
            self._ready = myntra_check.myntra_checker.is_ready
            logger.info("[Myntra] Ready — Chrome profile active via myntra_check")
        except Exception as exc:
            logger.error("[Myntra] Failed to start Chrome: %s", exc)
            self._ready = False

    async def shutdown(self) -> None:
        """Close Chrome context and persist state."""
        try:
            import sys
            root_str = str(_NEXCHECKER_DIR)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            import myntra_check

            await myntra_check.myntra_checker.shutdown()
        except Exception as exc:
            logger.warning("[Myntra] shutdown warning: %s", exc)
        self._ready = False

    # ── Check ─────────────────────────────────────────────────────────────────

    async def check_number(self, mobile: str) -> Dict[str, Any]:
        """Check a single mobile number against Myntra.

        Returns a dict with at minimum:
          {"status": "REGISTERED" | "NOT_REGISTERED" | "UNKNOWN" | "ERROR"}
        """
        async with self._lock:
            try:
                import sys
                root_str = str(_NEXCHECKER_DIR)
                if root_str not in sys.path:
                    sys.path.insert(0, root_str)
                from myntra_check import check_myntra  # type: ignore

                result = await check_myntra(mobile)
                return result
            except Exception as exc:
                logger.error("[Myntra] check_number error: %s", exc)
                return {"status": "ERROR", "mobile": mobile, "error": str(exc)}

    async def reload_page(self) -> None:
        """Reload /forgot page if needed."""
        try:
            import sys
            root_str = str(_NEXCHECKER_DIR)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            import myntra_check

            await myntra_check.myntra_checker.reload_page()
        except Exception as exc:
            logger.warning("[Myntra] reload_page error: %s", exc)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Module singleton ──────────────────────────────────────────────────────────
myntra_checker = MyntraChecker()
