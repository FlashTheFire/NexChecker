"""
NexBot — Scalable Hierarchical JSON Store
=========================================
Directory structure (scalable to millions of orders and thousands of users):
  data/users/{user_id}/
    ├── info.json              ← User profile, API key, preferences, stats, active_orders map
    ├── {order_id_1}.json      ← Isolated order record (e.g., 1791210961004126002825.json)
    ├── {order_id_2}.json
    └── ...

Features:
  • Zero collision between concurrent multi-service purchases (Zomato, Myntra, Flipkart, BigBasket)
  • Each order has its own atomic file — no huge monolithic JSON files rewritten on every poll
  • Automatic migration from legacy monolithic {user_id}.json on first access
  • Async file I/O executed via asyncio.to_thread with per-user asyncio.Lock
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR

logger = logging.getLogger(__name__)

# Per-user async lock to prevent race conditions during file updates
_locks: Dict[int, asyncio.Lock] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _locks:
        _locks[user_id] = asyncio.Lock()
    return _locks[user_id]


# ── Path Resolvers ────────────────────────────────────────────────────────────

def _user_dir(user_id: int) -> Path:
    return DATA_DIR / str(user_id)


def _info_path(user_id: int) -> Path:
    return _user_dir(user_id) / "info.json"


def _order_path(user_id: int, order_id: str) -> Path:
    return _user_dir(user_id) / f"{order_id}.json"


def _legacy_path(user_id: int) -> Path:
    return DATA_DIR / f"{user_id}.json"


# ── Default Schemas ───────────────────────────────────────────────────────────

def _default_info(user_id: int) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "api_key": None,
        "api_key_set_at": None,
        "active_orders": {
            "myntra": None,
            "bigbasket": None,
            "flipkart": None,
            "zomato": None,
        },
        "preferences": {
            "filter": "ANY",
            "max_attempts": 20,
        },
        "stats": {
            "total_checks": 0,
            "registered_found": 0,
            "not_registered_found": 0,
            "cancelled": 0,
        },
    }


def _default_order(order_id: str, user_id: int, platform: str = "zomato") -> Dict[str, Any]:
    return {
        "order_id": order_id,
        "user_id": user_id,
        "platform": platform,
        "number": None,
        "service": None,
        "country": "22",
        "cost": 0,
        "status": "CHECKING",  # CHECKING | REGISTERED | COMPLETED | REFUNDED | CANCELLED
        "check_result": None,  # REGISTERED | NOT_REGISTERED
        "last_otp": None,
        "last_full_sms": None,
        "otp_received_at": None,
        "seen_sms_ids": [],
        "attempt": 1,
        "message_id": None,
        "chat_id": user_id,
        "purchased_at": datetime.now(timezone.utc).isoformat(),
        "auto_cancelled": False,
        "finalized_at": None,
    }


# ── Sync Helpers (Run via asyncio.to_thread) ──────────────────────────────────

def _read_json_sync(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Corrupt JSON file %s: %s", path, exc)
        return None


def _write_json_sync(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic rename


def _migrate_legacy_user_sync(user_id: int) -> None:
    """Migrate legacy data/users/{user_id}.json to data/users/{user_id}/."""
    legacy = _legacy_path(user_id)
    if not legacy.is_file():
        return

    try:
        raw_data = json.loads(legacy.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to read legacy file %s for migration: %s", legacy, exc)
        return

    udir = _user_dir(user_id)
    udir.mkdir(parents=True, exist_ok=True)
    info_path = _info_path(user_id)

    # 1. Build info.json
    info = _default_info(user_id)
    info["api_key"] = raw_data.get("api_key")
    info["api_key_set_at"] = raw_data.get("api_key_set_at")
    info["preferences"].update(raw_data.get("preferences", {}))
    info["stats"].update(raw_data.get("stats", {}))

    # 2. Extract last_order
    last_order = raw_data.get("last_order", {})
    last_oid = last_order.get("order_id")
    if last_oid:
        pkey = last_order.get("platform", "myntra")
        info["active_orders"][pkey] = last_oid
        _write_json_sync(udir / f"{last_oid}.json", last_order)

    # 3. Extract purchases array into individual {order_id}.json files
    purchases = raw_data.get("purchases", [])
    for p in purchases:
        oid = p.get("order_id")
        if oid:
            opath = udir / f"{oid}.json"
            if not opath.exists():
                _write_json_sync(opath, p)

    # 4. Save info.json
    _write_json_sync(info_path, info)

    # 5. Safely archive/delete legacy monolithic file
    try:
        legacy.unlink(missing_ok=True)
        logger.info("Successfully migrated legacy user %d to hierarchical folder %s", user_id, udir)
    except Exception as exc:
        logger.warning("Could not delete legacy file %s after migration: %s", legacy, exc)


def _migrate_all_legacy_users_sync() -> int:
    """Scan and migrate all legacy monolithic user files on startup."""
    count = 0
    if not DATA_DIR.is_dir():
        return count

    for item in DATA_DIR.glob("*.json"):
        if item.is_file() and item.stem.isdigit():
            try:
                uid = int(item.stem)
                _migrate_legacy_user_sync(uid)
                count += 1
            except Exception as exc:
                logger.warning("Failed migrating legacy file %s: %s", item, exc)
    return count


# ── Public User Info API ──────────────────────────────────────────────────────

async def load_user_info(user_id: int) -> Dict[str, Any]:
    """Load user info; auto-migrates if legacy monolithic file exists."""
    path = _info_path(user_id)
    if not path.is_file() and _legacy_path(user_id).is_file():
        await asyncio.to_thread(_migrate_legacy_user_sync, user_id)

    data = await asyncio.to_thread(_read_json_sync, path)
    if data is None:
        return _default_info(user_id)
    return data


async def save_user_info(user_id: int, data: Dict[str, Any]) -> None:
    """Save user info atomically."""
    async with _get_lock(user_id):
        await asyncio.to_thread(_write_json_sync, _info_path(user_id), data)


async def get_api_key(user_id: int) -> Optional[str]:
    """Return stored API key for user."""
    info = await load_user_info(user_id)
    return info.get("api_key")


async def set_api_key(user_id: int, api_key: str) -> None:
    """Persist new NexNum API key."""
    async with _get_lock(user_id):
        info = await load_user_info(user_id)
        info["api_key"] = api_key
        info["api_key_set_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)


async def delete_api_key(user_id: int) -> None:
    """Remove stored API key."""
    async with _get_lock(user_id):
        info = await load_user_info(user_id)
        info["api_key"] = None
        info["api_key_set_at"] = None
        await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)


async def set_preference(user_id: int, key: str, value: Any) -> None:
    async with _get_lock(user_id):
        info = await load_user_info(user_id)
        info.setdefault("preferences", {})[key] = value
        await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)


async def get_preference(user_id: int, key: str, default: Any = None) -> Any:
    info = await load_user_info(user_id)
    return info.get("preferences", {}).get(key, default)


async def get_stats(user_id: int) -> Dict[str, Any]:
    info = await load_user_info(user_id)
    return info.get("stats", {})


async def increment_stat(user_id: int, status: str) -> None:
    """Increment user stats counters."""
    async with _get_lock(user_id):
        info = await load_user_info(user_id)
        stats = info.setdefault("stats", {
            "total_checks": 0, "registered_found": 0,
            "not_registered_found": 0, "cancelled": 0,
        })
        stats["total_checks"] = stats.get("total_checks", 0) + 1
        if status == "REGISTERED":
            stats["registered_found"] = stats.get("registered_found", 0) + 1
        elif status == "NOT_REGISTERED":
            stats["not_registered_found"] = stats.get("not_registered_found", 0) + 1
        elif status == "cancelled":
            stats["total_checks"] = max(0, stats["total_checks"] - 1)
            stats["cancelled"] = stats.get("cancelled", 0) + 1
        await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)


# ── Public Order API (Per-Order JSON Files) ───────────────────────────────────

async def get_order(user_id: int, order_id: str) -> Optional[Dict[str, Any]]:
    """Load a specific order file {user_id}/{order_id}.json."""
    if not order_id:
        return None
    path = _order_path(user_id, order_id)
    return await asyncio.to_thread(_read_json_sync, path)


async def save_order(order: Dict[str, Any]) -> None:
    """Save or create an order file."""
    user_id = int(order.get("user_id") or order.get("chat_id", 0))
    order_id = str(order.get("order_id", ""))
    if not user_id or not order_id:
        return

    path = _order_path(user_id, order_id)
    async with _get_lock(user_id):
        await asyncio.to_thread(_write_json_sync, path, order)
        # Also register as active order for this platform
        platform = order.get("platform")
        if platform:
            info = await load_user_info(user_id)
            info.setdefault("active_orders", {})[platform] = order_id
            await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)


async def update_order(user_id: int, order_payload: Dict[str, Any], order_id: Optional[str] = None) -> Dict[str, Any]:
    """Merge updates into an existing or active order file."""
    oid = order_id or order_payload.get("order_id")
    pkey = order_payload.get("platform")

    async with _get_lock(user_id):
        info = await load_user_info(user_id)

        # Resolve order_id if not explicitly provided
        if not oid and pkey:
            oid = info.get("active_orders", {}).get(pkey)

        if not oid:
            # Fallback to the latest order if available
            for active_oid in info.get("active_orders", {}).values():
                if active_oid:
                    oid = active_oid
                    break

        if not oid:
            # Create a placeholder if none exists
            oid = f"temp_{int(datetime.now().timestamp())}"
            order_payload["order_id"] = oid

        path = _order_path(user_id, oid)
        existing = await asyncio.to_thread(_read_json_sync, path)
        if existing is None:
            existing = _default_order(oid, user_id, pkey or "zomato")

        existing.update(order_payload)

        # Check terminal status transition
        if existing.get("status") in ("COMPLETED", "REFUNDED", "CANCELLED") and not existing.get("finalized_at"):
            existing["finalized_at"] = datetime.now(timezone.utc).isoformat()

        await asyncio.to_thread(_write_json_sync, path, existing)

        # Update active_orders pointer
        if pkey:
            info.setdefault("active_orders", {})[pkey] = oid
            await asyncio.to_thread(_write_json_sync, _info_path(user_id), info)

        return existing


async def get_active_order(user_id: int, platform: str) -> Optional[Dict[str, Any]]:
    """Return the active in-flight or latest order for a specific platform."""
    info = await load_user_info(user_id)
    oid = info.get("active_orders", {}).get(platform)
    if not oid:
        return None
    return await get_order(user_id, oid)


async def get_last_order(user_id: int, platform: Optional[str] = None) -> Dict[str, Any]:
    """Backward compatibility wrapper — returns active order for platform, or most recent."""
    if platform:
        res = await get_active_order(user_id, platform)
        if res:
            return res

    # Otherwise scan user directory for the newest order
    orders = await get_all_orders(user_id, limit=1)
    if orders:
        return orders[0]
    return {}


async def get_all_orders(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Return all orders for a user, sorted newest first."""
    udir = _user_dir(user_id)
    if not udir.is_dir():
        # Check if legacy migration needed
        if _legacy_path(user_id).is_file():
            await asyncio.to_thread(_migrate_legacy_user_sync, user_id)
        if not udir.is_dir():
            return []

    def _load_all() -> List[Dict[str, Any]]:
        out = []
        for f in udir.glob("*.json"):
            if f.name == "info.json" or f.name.endswith(".tmp"):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                out.append(data)
            except Exception:
                continue
        out.sort(key=lambda x: x.get("purchased_at") or "", reverse=True)
        return out[:limit]

    return await asyncio.to_thread(_load_all)


async def load_all_active_orders(max_age_minutes: int = 19) -> List[Dict[str, Any]]:
    """Scan all user order files across the entire store to resume active pollers."""
    from datetime import timedelta

    # Perform startup migration first
    await asyncio.to_thread(_migrate_all_legacy_users_sync)

    results: List[Dict[str, Any]] = []
    if not DATA_DIR.is_dir():
        return results

    def _scan_sync() -> List[Dict[str, Any]]:
        active_list = []
        now_utc = datetime.now(timezone.utc)

        for udir in DATA_DIR.iterdir():
            if not udir.is_dir():
                continue
            info_file = udir / "info.json"
            if not info_file.is_file():
                continue
            info = _read_json_sync(info_file)
            api_key = info.get("api_key") if info else None
            if not api_key:
                continue

            for ofile in udir.glob("*.json"):
                if ofile.name == "info.json" or ofile.name.endswith(".tmp"):
                    continue
                order = _read_json_sync(ofile)
                if not order:
                    continue

                status = order.get("status")
                if status not in ("REGISTERED", "CHECKING", "COMPLETED"):
                    continue
                if not all(order.get(k) for k in ("order_id", "number", "message_id", "chat_id")):
                    continue

                purchased_at_str = order.get("purchased_at")
                if not purchased_at_str:
                    continue

                try:
                    purchased_at = datetime.fromisoformat(purchased_at_str)
                    if purchased_at.tzinfo is None:
                        purchased_at = purchased_at.replace(tzinfo=timezone.utc)
                    age = now_utc - purchased_at
                    if age > timedelta(minutes=max_age_minutes):
                        continue
                except Exception:
                    continue

                active_list.append({
                    "user_id": int(order.get("user_id") or order["chat_id"]),
                    "platform": order.get("platform", "zomato"),
                    "api_key": api_key,
                    "order_id": str(order["order_id"]),
                    "number": str(order["number"]),
                    "message_id": int(order["message_id"]),
                    "chat_id": int(order["chat_id"]),
                    "status": status,
                    "cost": order.get("cost", 0),
                    "attempt": order.get("attempt", 1),
                    "last_otp": order.get("last_otp"),
                    "last_full_sms": order.get("last_full_sms", ""),
                    "purchased_at": purchased_at_str,
                    "check_result": order.get("check_result") or order.get("myn_result", ""),
                    "seen_sms_ids": order.get("seen_sms_ids", []),
                })
        return active_list

    return await asyncio.to_thread(_scan_sync)
