"""NexBot — BigBasket checker API wrapper.

Wraps bigbasket_check.py into the same interface as MyntraChecker:
  - check_number(mobile) → {"status": "REGISTERED"|"NOT_REGISTERED"|"UNKNOWN"|"ERROR", ...}
  - startup()  → loads/validates bb_state.json
  - shutdown() → no-op (no persistent Chrome context)
  - is_ready   → True once state file is confirmed present

No Playwright warmup needed — HTTP-first approach, real Chrome is only used
as a fallback when the HTTP method is blocked (handled inside check_bigbasket()).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Resolve bb_state.json relative to the NexChecker root (one level above NexBot)
_NEXCHECKER_DIR = Path(__file__).resolve().parent.parent.parent
_BB_STATE_FILE  = _NEXCHECKER_DIR / "bb_state.json"


class BigBasketChecker:
    """Manages BigBasket registration checks.

    Delegates to check_bigbasket() from bigbasket_check.py.
    Uses asyncio.Lock to serialise concurrent checks (the HTTP client is
    stateless, but the file-system state load is cheap — keep it simple).
    """

    def __init__(self) -> None:
        self._lock  = asyncio.Lock()
        self._ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Validate that bb_state.json exists.  No Chrome needed."""
        if _BB_STATE_FILE.exists():
            self._ready = True
            logger.info("[BigBasket] Ready — state file found: %s", _BB_STATE_FILE.name)
        else:
            self._ready = False
            logger.warning(
                "[BigBasket] bb_state.json NOT found at %s — "
                "run bb_save_state.py once to create it. "
                "BigBasket checker will return BLOCKED until the file exists.",
                _BB_STATE_FILE,
            )

    async def shutdown(self) -> None:
        """No-op — BigBasket has no persistent browser context to close."""
        self._ready = False

    # ── Check ─────────────────────────────────────────────────────────────────

    async def check_number(self, mobile: str) -> Dict[str, Any]:
        """Check a single mobile number against BigBasket.

        Returns a dict with at minimum:
          {"status": "REGISTERED" | "NOT_REGISTERED" | "UNKNOWN" | "ERROR" | "BLOCKED"}
        """
        # Re-check state file on every call so a late-added file is picked up
        # without needing a bot restart.
        if not _BB_STATE_FILE.exists():
            self._ready = False
            return {
                "status": "BLOCKED",
                "mobile": mobile,
                "error":  "bb_state.json missing — run bb_save_state.py first",
            }

        self._ready = True

        async with self._lock:
            try:
                # Lazy import — bigbasket_check.py lives in the NexChecker root,
                # which is on sys.path via bot.py's ROOT insertion.
                import sys
                nexchecker_root = str(_NEXCHECKER_DIR)
                if nexchecker_root not in sys.path:
                    sys.path.insert(0, nexchecker_root)
                from bigbasket_check import check_bigbasket  # type: ignore
                result = await check_bigbasket(mobile)
                return result
            except Exception as exc:
                logger.error("[BigBasket] check_number error: %s", exc)
                return {"status": "ERROR", "mobile": mobile, "error": str(exc)}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Module singleton ──────────────────────────────────────────────────────────
bigbasket_checker = BigBasketChecker()
