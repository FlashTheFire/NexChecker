"""NexBot — Per-user JSON store.

One file per user: data/users/{user_id}.json
All reads/writes are wrapped in asyncio.to_thread() to avoid blocking the
event loop. A per-user asyncio.Lock prevents write races.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from utils.config import DATA_DIR

logger = logging.getLogger(__name__)

# ── Per-user locks (prevents concurrent writes to the same file) ──────────────
_locks: Dict[int, asyncio.Lock] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _locks:
        _locks[user_id] = asyncio.Lock()
    return _locks[user_id]


def _user_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


# ── Default schema ────────────────────────────────────────────────────────────

def _default_data(user_id: int) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "api_key": None,
        "api_key_set_at": None,
        "last_order": {
            "platform":      "myntra",  # platform key — default for backward compat
            "order_id":      None,
            "number":        None,
            "service":       None,
            "country":       None,
            "cost":          0,
            "status":        None,    # CHECKING | REGISTERED | COMPLETED | REFUNDED
            "last_otp":      None,    # last OTP code received
            "last_full_sms": None,    # full SMS text (persisted for copy button after restart)
            "otp_received_at": None,  # ISO timestamp of first OTP
            "attempt":       0,
            "message_id":    None,
            "chat_id":       None,
            "purchased_at":  None,
        },
        "purchases": [],              # full history — one entry per finalized order
        "preferences": {
            "filter":       "ANY",
            "max_attempts": 20,
        },
        "stats": {
            "total_checks":          0,
            "registered_found":      0,
            "not_registered_found":  0,
            "cancelled":             0,
        },
    }


# ── Sync helpers (run inside asyncio.to_thread) ───────────────────────────────

def _read_sync(path: Path, user_id: int) -> Dict[str, Any]:
    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt user file %s: %s — resetting", path, exc)
    return _default_data(user_id)


def _write_sync(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic rename


# ── Public async API ──────────────────────────────────────────────────────────

async def load_user(user_id: int) -> Dict[str, Any]:
    """Load user data; returns default schema if file doesn't exist."""
    path = _user_path(user_id)
    return await asyncio.to_thread(_read_sync, path, user_id)


async def save_user(user_id: int, data: Dict[str, Any]) -> None:
    """Atomically write user data."""
    path = _user_path(user_id)
    async with _get_lock(user_id):
        await asyncio.to_thread(_write_sync, path, data)


async def get_api_key(user_id: int) -> Optional[str]:
    """Return the stored API key, or None if not set."""
    data = await load_user(user_id)
    return data.get("api_key")


async def set_api_key(user_id: int, api_key: str) -> None:
    """Persist a new API key for the user."""
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        data["api_key"] = api_key
        data["api_key_set_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(_write_sync, path, data)


async def delete_api_key(user_id: int) -> None:
    """Remove the stored API key."""
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        data["api_key"] = None
        data["api_key_set_at"] = None
        await asyncio.to_thread(_write_sync, path, data)


async def update_order(user_id: int, order: Dict[str, Any]) -> None:
    """Merge ``order`` dict into last_order and save.

    Whenever a terminal status (COMPLETED / REFUNDED) is written for the
    first time on an order, a snapshot is automatically appended to
    ``purchases[]`` so the full history is preserved.
    """
    TERMINAL = ("COMPLETED", "REFUNDED")
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        prev_status = data["last_order"].get("status")
        data["last_order"].update(order)
        new_status  = data["last_order"].get("status")

        # Auto-append to purchases[] when an order first reaches a terminal state
        if new_status in TERMINAL and prev_status not in TERMINAL:
            _append_purchase_sync(data)

        await asyncio.to_thread(_write_sync, path, data)


async def get_last_order(user_id: int) -> Dict[str, Any]:
    data = await load_user(user_id)
    return data.get("last_order", {})


async def set_preference(user_id: int, key: str, value: Any) -> None:
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        data["preferences"][key] = value
        await asyncio.to_thread(_write_sync, path, data)


async def get_preference(user_id: int, key: str, default: Any = None) -> Any:
    data = await load_user(user_id)
    return data.get("preferences", {}).get(key, default)


async def increment_stat(user_id: int, status: str) -> None:
    """Increment one of the stats counters based on check result status."""
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        stats = data.setdefault("stats", {
            "total_checks": 0, "registered_found": 0,
            "not_registered_found": 0, "cancelled": 0,
        })
        stats["total_checks"] = stats.get("total_checks", 0) + 1
        if status == "REGISTERED":
            stats["registered_found"] = stats.get("registered_found", 0) + 1
        elif status == "NOT_REGISTERED":
            stats["not_registered_found"] = stats.get("not_registered_found", 0) + 1
        elif status == "cancelled":
            stats["total_checks"] = max(0, stats["total_checks"] - 1)  # don't count cancelled as check
            stats["cancelled"] = stats.get("cancelled", 0) + 1
        await asyncio.to_thread(_write_sync, path, data)


async def get_stats(user_id: int) -> Dict[str, Any]:
    data = await load_user(user_id)
    return data.get("stats", {})


# ── Purchase history ──────────────────────────────────────────────────────────

def _append_purchase_sync(data: Dict[str, Any]) -> None:
    """Append a snapshot of last_order to purchases[].  Called inside the lock.

    Only records orders that have an order_id (i.e. real purchases, not
    IDLE placeholders).  Deduplicates by order_id so double-calls are safe.
    """
    order = data.get("last_order", {})
    order_id = order.get("order_id")
    if not order_id:
        return

    purchases: list = data.setdefault("purchases", [])

    # Dedup: if we already have an entry for this order_id, update it in-place
    for i, p in enumerate(purchases):
        if p.get("order_id") == order_id:
            purchases[i] = _purchase_snapshot(order)
            return

    purchases.append(_purchase_snapshot(order))


def _purchase_snapshot(order: Dict[str, Any]) -> Dict[str, Any]:
    """Build a clean purchase record from a last_order dict."""
    return {
        "platform":      order.get("platform", "myntra"),  # ← include platform
        "order_id":      order.get("order_id"),
        "number":        order.get("number"),
        "service":       order.get("service"),
        "country":       order.get("country"),
        "cost":          order.get("cost", 0),
        "status":        order.get("status"),           # COMPLETED / REFUNDED
        "myn_result":    order.get("myn_result", ""),   # REGISTERED / NOT_REGISTERED
        "last_otp":      order.get("last_otp", ""),
        "last_full_sms": order.get("last_full_sms", ""),
        "otp_received_at": order.get("otp_received_at"),
        "attempt":       order.get("attempt", 1),
        "purchased_at":  order.get("purchased_at"),
        "auto_cancelled": order.get("auto_cancelled", False),
        "finalized_at":  datetime.now(timezone.utc).isoformat(),
    }


async def append_purchase(user_id: int) -> None:
    """Public helper — manually append the current last_order to purchases[].

    Use this when the auto-trigger in update_order() doesn't fire
    (e.g., status was already terminal on a previous write).
    """
    async with _get_lock(user_id):
        path = _user_path(user_id)
        data = await asyncio.to_thread(_read_sync, path, user_id)
        _append_purchase_sync(data)
        await asyncio.to_thread(_write_sync, path, data)


async def get_purchases(user_id: int) -> list:
    """Return full purchase history for a user, newest first."""
    data = await load_user(user_id)
    return list(reversed(data.get("purchases", [])))


async def load_all_active_orders(max_age_minutes: int = 19) -> list[Dict[str, Any]]:
    """Scan all user JSON files and return orders needing startup handling.

    Returns:
      - REGISTERED / CHECKING  -> resume poller (may still get OTP)
      - COMPLETED              -> re-edit card with saved OTP (no poller needed)

    Side-effect: migrates any file missing purchases[] on first startup.
    """
    from datetime import timedelta
    results = []
    if not DATA_DIR.exists():
        return results

    for path in DATA_DIR.glob("*.json"):
        try:
            user_id = int(path.stem)
        except ValueError:
            continue
        try:
            data    = await asyncio.to_thread(_read_sync, path, 0)
            order   = data.get("last_order", {})
            api_key = data.get("api_key")

            # -- Startup migration: add purchases[] if missing
            if "purchases" not in data:
                data["purchases"] = []
                if order.get("status") in ("COMPLETED", "REFUNDED") and order.get("order_id"):
                    _append_purchase_sync(data)
                await asyncio.to_thread(_write_sync, path, data)
                logger.info("user_store: migrated purchases[] for user=%s", user_id)

            if not api_key:
                continue

            status = order.get("status")
            if status not in ("REGISTERED", "CHECKING", "COMPLETED"):
                continue
            if not all(order.get(k) for k in ("order_id", "number", "message_id", "chat_id")):
                continue

            purchased_at_str = order.get("purchased_at")
            if not purchased_at_str:
                continue

            purchased_at = datetime.fromisoformat(purchased_at_str)
            if purchased_at.tzinfo is None:
                purchased_at = purchased_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - purchased_at
            if age > timedelta(minutes=max_age_minutes):
                continue

            results.append({
                "user_id":       user_id,
                "platform":      order.get("platform", "myntra"),  # ← platform key
                "api_key":       api_key,
                "order_id":      order["order_id"],
                "number":        order["number"],
                "message_id":    int(order["message_id"]),
                "chat_id":       int(order["chat_id"]),
                "status":        status,
                "cost":          order.get("cost",         0),
                "attempt":       order.get("attempt",      1),
                "last_otp":      order.get("last_otp"),
                "last_full_sms": order.get("last_full_sms", ""),
                "purchased_at":  purchased_at_str,
                "myn_result":    order.get("myn_result", ""),
            })
        except Exception as exc:
            logger.warning("load_all_active_orders: skipping %s: %s", path, exc)

    return results
