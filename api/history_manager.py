"""NexChecker — High-Class Server-Side JSON History Engine.

Provides secure, disk-backed, atomic JSON history management for both
authenticated Telegram WebApp users and guest visitors.

Features:
  - Strict user partitioning: each user's history is isolated in data/server_history/users/<user_id>.json.
  - Global user registry and activity tracking in data/server_history/users_index.json.
  - Atomic writes (write to temp file then replace) to ensure data integrity.
  - Asynchronous concurrency control with asyncio.Lock.
  - Rich metadata tracking (exact timestamps, latency, brand details, registration status).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.auth import UserIdentity

logger = logging.getLogger("NexChecker.History")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = PROJECT_ROOT / "data" / "server_history"
USERS_DIR = HISTORY_DIR / "users"
USERS_INDEX_FILE = HISTORY_DIR / "users_index.json"

_lock = asyncio.Lock()


def _ensure_directories() -> None:
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_INDEX_FILE.exists():
        initial = {
            "total_users": 0,
            "total_checks": 0,
            "users": {},
            "created_at": int(time.time()),
            "last_updated": int(time.time()),
        }
        USERS_INDEX_FILE.write_text(json.dumps(initial, indent=2, ensure_ascii=False), encoding="utf-8")


def _atomic_write_json(file_path: Path, data: Any) -> None:
    """Safely write JSON using an atomic replace operation."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(f".tmp.{secrets.token_hex(4)}")
    temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_file.replace(file_path)


def _load_json(file_path: Path, default: Any) -> Any:
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to read JSON from %s: %s", file_path, exc)
        return default


class ServerHistoryManager:
    """Manages all server-side check history and user metrics."""

    def __init__(self) -> None:
        _ensure_directories()

    async def record_check(
        self,
        user: UserIdentity,
        phone: str,
        platform: str,
        brand_name: str,
        registered: bool,
        fresh: bool,
        status: str,
        details: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record a single phone check to user's server history and update the global index."""
        now_ts = int(time.time())
        now_iso = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()
        record_id = f"chk_{now_ts}_{secrets.token_hex(3)}"

        clean_phone = "".join(c for c in phone if c.isdigit())[-10:]

        record = {
            "id": record_id,
            "phone": clean_phone,
            "platform": platform.lower(),
            "brand_name": brand_name,
            "registered": bool(registered),
            "fresh": bool(fresh),
            "status": status.upper(),
            "details": details or ("Registered" if registered else "Fresh / Available"),
            "timestamp": now_ts,
            "iso_time": now_iso,
            "latency_ms": latency_ms or 0,
        }

        async with _lock:
            # 1. Update user's personal history file
            user_file = USERS_DIR / f"{user.user_id}.json"
            user_doc = _load_json(user_file, {
                "user_id": user.user_id,
                "auth_type": user.auth_type,
                "username": user.username,
                "first_name": user.first_name,
                "telegram_id": user.telegram_id,
                "created_at": now_ts,
                "last_active": now_ts,
                "total_checks": 0,
                "records": [],
            })

            user_doc["last_active"] = now_ts
            user_doc["username"] = user.username or user_doc.get("username")
            user_doc["first_name"] = user.first_name or user_doc.get("first_name")
            user_doc["total_checks"] = user_doc.get("total_checks", 0) + 1

            records: List[Dict[str, Any]] = user_doc.get("records", [])
            records.insert(0, record)
            # Retain the most recent 100 entries per user
            user_doc["records"] = records[:100]

            _atomic_write_json(user_file, user_doc)

            # 2. Update global users index
            index = _load_json(USERS_INDEX_FILE, {
                "total_users": 0,
                "total_checks": 0,
                "users": {},
            })

            index["total_checks"] = index.get("total_checks", 0) + 1
            users_map = index.setdefault("users", {})

            if user.user_id not in users_map:
                users_map[user.user_id] = {
                    "user_id": user.user_id,
                    "auth_type": user.auth_type,
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "first_seen": now_ts,
                    "last_seen": now_ts,
                    "total_checks": 1,
                    "platforms": {platform: 1},
                    "ip_address": user.ip_address,
                }
            else:
                entry = users_map[user.user_id]
                entry["last_seen"] = now_ts
                entry["total_checks"] = entry.get("total_checks", 0) + 1
                if user.username:
                    entry["username"] = user.username
                if user.first_name:
                    entry["first_name"] = user.first_name
                if user.ip_address:
                    entry["ip_address"] = user.ip_address
                entry.setdefault("platforms", {})[platform] = entry.get("platforms", {}).get(platform, 0) + 1

            index["total_users"] = len(users_map)
            index["last_updated"] = now_ts
            _atomic_write_json(USERS_INDEX_FILE, index)

        return record

    async def get_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent history records for a user."""
        user_file = USERS_DIR / f"{user_id}.json"
        user_doc = _load_json(user_file, {})
        records = user_doc.get("records", [])
        return records[:limit]

    async def clear_history(self, user_id: str) -> bool:
        """Clear all records for a user while preserving profile stats."""
        user_file = USERS_DIR / f"{user_id}.json"
        if not user_file.exists():
            return True

        async with _lock:
            user_doc = _load_json(user_file, {})
            user_doc["records"] = []
            user_doc["last_active"] = int(time.time())
            _atomic_write_json(user_file, user_doc)
        return True

    async def delete_item(self, user_id: str, record_id: str) -> bool:
        """Delete a single specific history record."""
        user_file = USERS_DIR / f"{user_id}.json"
        if not user_file.exists():
            return False

        async with _lock:
            user_doc = _load_json(user_file, {})
            records = [r for r in user_doc.get("records", []) if r.get("id") != record_id]
            user_doc["records"] = records
            _atomic_write_json(user_file, user_doc)
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregate metrics across all users."""
        return _load_json(USERS_INDEX_FILE, {
            "total_users": 0,
            "total_checks": 0,
            "users": {},
        })


# Global singleton instance
history_manager = ServerHistoryManager()
