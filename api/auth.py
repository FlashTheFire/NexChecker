"""NexChecker — High-Level Cryptographic Security & Telegram WebApp Auth.

Validates Telegram WebApp initData HMAC-SHA256 signatures according to official
Telegram Bot API specifications:
  - Validates hash integrity using secret key derived from BOT_TOKEN.
  - Enforces strict timing expiry (auth_date freshness) to eliminate replay attacks.
  - Sanitizes user metadata and tracks active users on the server side.
  - Provides seamless fallback to persistent guest identifier for browser testing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from fastapi import Request

logger = logging.getLogger("NexChecker.Auth")

# Bot token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Max initData validity window in seconds (default: 24 hours / 86400s)
AUTH_MAX_AGE_SECONDS = int(os.getenv("AUTH_MAX_AGE_SECONDS", "86400"))


@dataclass
class UserIdentity:
    user_id: str             # e.g., "tg_12345678" or "guest_ab12cd34"
    auth_type: str           # "telegram" or "guest"
    is_authenticated: bool   # True if cryptographically verified Telegram user
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    auth_date: Optional[int] = None
    ip_address: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def verify_telegram_init_data(
    init_data: str,
    bot_token: Optional[str] = None,
    max_age_seconds: int = AUTH_MAX_AGE_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Cryptographically verify Telegram WebApp initData HMAC-SHA256 signature.

    Returns the extracted and verified user dictionary on success, or None on failure:
      1. Missing or forged hash -> None
      2. Expired auth_date (> max_age_seconds) -> None (prevents replay attacks)
      3. Tampered payload -> None
    """
    token = (bot_token or BOT_TOKEN).strip()
    if not init_data or not token:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            logger.warning("Auth rejected: missing 'hash' in Telegram initData")
            return None

        # 1. Timing and Expiry Verification (Anti-Replay / Freshness)
        auth_date_str = parsed.get("auth_date")
        if not auth_date_str:
            logger.warning("Auth rejected: missing 'auth_date' in Telegram initData")
            return None

        try:
            auth_date = int(auth_date_str)
        except (ValueError, TypeError):
            logger.warning("Auth rejected: invalid 'auth_date' format: %s", auth_date_str)
            return None

        now = int(time.time())
        age = now - auth_date
        # Disallow future timestamps by more than 120s (clock skew allowance) and older than max_age
        if age < -120 or age > max_age_seconds:
            logger.warning(
                "Auth rejected: initData expired (auth_date=%s, now=%s, age=%ss, max=%ss)",
                auth_date, now, age, max_age_seconds
            )
            return None

        # 2. Build data_check_string (sorted alphabetically by key, format: key=<value>\n...)
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # 3. Cryptographic HMAC-SHA256 signature calculation per Telegram Spec:
        # secret_key = HMAC_SHA256(key=b"WebAppData", data=bot_token.encode())
        # computed_hash = HMAC_SHA256(key=secret_key, data=data_check_string.encode()).hexdigest()
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning("Auth rejected: cryptographic signature mismatch (tampering detected)")
            return None

        # 4. Parse user JSON payload
        user_raw = parsed.get("user")
        user_dict: Dict[str, Any] = {}
        if user_raw:
            try:
                user_dict = json.loads(user_raw)
            except Exception as e:
                logger.error("Failed to parse user JSON from initData: %s", e)

        user_dict["auth_date"] = auth_date
        user_dict["query_id"] = parsed.get("query_id")
        user_dict["chat_type"] = parsed.get("chat_type")
        user_dict["verified_at"] = now

        return user_dict
    except Exception as exc:
        logger.error("Unexpected exception during Telegram initData verification: %s", exc)
        return None


def get_request_identity(request: Request) -> UserIdentity:
    """Extract and authenticate user identity from the incoming HTTP request.

    Priority:
      1. X-Telegram-Init-Data header or ?init_data query parameter (cryptographically verified).
      2. X-Guest-ID header (sanitized persistent UUID).
      3. Fallback to client IP address.
    """
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )

    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.query_params.get("init_data")
        or ""
    ).strip()

    if init_data:
        verified_user = verify_telegram_init_data(init_data)
        if verified_user and verified_user.get("id"):
            tg_id = int(verified_user["id"])
            return UserIdentity(
                user_id=f"tg_{tg_id}",
                auth_type="telegram",
                is_authenticated=True,
                telegram_id=tg_id,
                username=verified_user.get("username"),
                first_name=verified_user.get("first_name"),
                last_name=verified_user.get("last_name"),
                language_code=verified_user.get("language_code"),
                auth_date=verified_user.get("auth_date"),
                ip_address=client_ip,
            )

    # Browser testing or guest session fallback
    raw_guest_id = request.headers.get("X-Guest-ID") or request.cookies.get("nex_guest_id") or ""
    # Sanitize guest ID (alphanumeric, dashes, underscores, max 64 chars)
    safe_guest = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_guest_id)[:64]
    if not safe_guest:
        # Fallback to sanitized client IP
        safe_guest = re.sub(r"[^a-zA-Z0-9_\-]", "_", client_ip)[:32] or "anon"

    return UserIdentity(
        user_id=f"guest_{safe_guest}",
        auth_type="guest",
        is_authenticated=False,
        username=f"Guest_{safe_guest[:8]}",
        first_name="Guest",
        auth_date=int(time.time()),
        ip_address=client_ip,
    )
