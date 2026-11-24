"""NexChecker — Targeted Purchase Service Engine.
==============================================
Acquires virtual phone numbers from NexNum and filters them based on
platform registration checks (e.g., only NOT_REGISTERED or only REGISTERED).

If a purchased number does not match target status, it is immediately
submitted to the deferred cancellation engine for refund, and the loop
proceeds to the next number until matched or max attempts reached.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

# Bootstrap path resolution
_ROOT = Path(__file__).resolve().parent.parent
_NEXBOT_ROOT = _ROOT / "NexBot"
for _p in (str(_ROOT), str(_NEXBOT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.cancel_queue import cancel_queue

try:
    from NexBot.core.nexnum_api import NexNumStatus, nexnum_client
    from NexBot.utils.config import (
        BIGBASKET_SERVICE_CODE,
        FLIPKART_SERVICE_CODE,
        MYNTRA_SERVICE_CODE,
        ZOMATO_SERVICE_CODE,
    )
except ImportError:
    from core.nexnum_api import NexNumStatus, nexnum_client  # type: ignore
    from utils.config import (  # type: ignore
        BIGBASKET_SERVICE_CODE,
        FLIPKART_SERVICE_CODE,
        MYNTRA_SERVICE_CODE,
        ZOMATO_SERVICE_CODE,
    )

logger = logging.getLogger("NexChecker.PurchaseService")

# Platform defaults for NexNum service codes
DEFAULT_PLATFORM_SERVICES: Dict[str, str] = {
    "zomato": ZOMATO_SERVICE_CODE or "dy",
    "flipkart": FLIPKART_SERVICE_CODE or "xt",
    "myntra": MYNTRA_SERVICE_CODE or "nl",
    "bigbasket": BIGBASKET_SERVICE_CODE or "bb",
    "amazon": os.getenv("AMAZON_SERVICE_CODE", "am"),
    "swiggy": os.getenv("SWIGGY_SERVICE_CODE", "sw"),
    "meesho": os.getenv("MEESHO_SERVICE_CODE", "me"),
    "zepto": os.getenv("ZEPTO_SERVICE_CODE", "zp"),
}

NEXNUM_HANDLER_URL = os.getenv("NEXNUM_BASE_URL", "https://nexnum.in/stubs/handler_api.php")


class PurchaseRequest(BaseModel):
    platform: str = Field("zomato", description="Target platform (e.g. zomato, flipkart, myntra, meesho, etc.)")
    target_status: str = Field("NOT_REGISTERED", description="Desired status: NOT_REGISTERED or REGISTERED")
    service_code: Optional[str] = Field(None, description="NexNum service code override (e.g. 2426, dy, nl)")
    country_code: str = Field("22", description="NexNum country code (default 22 for India)")
    max_attempts: int = Field(5, ge=1, le=20, description="Max acquisition attempts before stopping")
    api_key: Optional[str] = Field(None, description="NexNum API key (can also be passed via X-NexNum-Key header)")


def extract_10(phone: str) -> str:
    """Extract clean 10-digit Indian mobile number."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("91") and len(digits) >= 12:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


async def execute_targeted_purchase(
    req: PurchaseRequest,
    nexnum_key: str,
    checker_fn: Callable[[str, str], Any],
) -> Dict[str, Any]:
    """Execute the purchase-and-filter loop.

    Args:
        req: Validated PurchaseRequest parameters.
        nexnum_key: NexNum API key provided by the caller.
        checker_fn: Async callable taking (platform, clean_mobile) returning dict with 'status'.

    Returns:
        Structured response dictionary matching approved API specification.
    """
    key = (nexnum_key or req.api_key or "").strip()
    if not key:
        return {
            "success": False,
            "error": "NEXNUM_KEY_REQUIRED",
            "message": "Missing NexNum API key. Provide via 'X-NexNum-Key' header or 'api_key' in JSON body.",
        }

    platform = req.platform.lower().strip()
    target_status = req.target_status.upper().strip()
    if target_status not in ("REGISTERED", "NOT_REGISTERED"):
        return {
            "success": False,
            "error": "INVALID_TARGET_STATUS",
            "message": f"Target status '{target_status}' is invalid. Must be 'REGISTERED' or 'NOT_REGISTERED'.",
        }

    service_code = (req.service_code or DEFAULT_PLATFORM_SERVICES.get(platform, "dy")).strip()
    country_code = req.country_code.strip() or "22"
    max_attempts = req.max_attempts

    discarded_orders: List[Dict[str, Any]] = []
    consecutive_inconclusive_count = 0
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        logger.info(
            "[Purchase] Attempt %d/%d for platform '%s' (target: %s, service: %s)",
            attempt, max_attempts, platform, target_status, service_code
        )

        buy = await nexnum_client.get_number(key, service=service_code, country=country_code)

        if not buy.get("ok"):
            err_code = buy.get("status") or buy.get("error") or "UNKNOWN_ERROR"
            logger.warning("[Purchase] NexNum get_number failed: %s (%s)", err_code, buy.get("error"))

            # Fatal account/auth errors stop immediately
            if err_code in (NexNumStatus.BAD_KEY, NexNumStatus.NO_BALANCE, NexNumStatus.BANNED):
                return {
                    "success": False,
                    "error": str(err_code),
                    "message": f"NexNum error: {buy.get('error', err_code)}",
                    "attempts_taken": attempt,
                    "discarded_orders": discarded_orders,
                }

            if err_code == NexNumStatus.NO_NUMBERS:
                # Retry if attempts remain
                if attempt >= max_attempts:
                    return {
                        "success": False,
                        "error": "NO_NUMBERS",
                        "message": f"NexNum has no numbers available for service '{service_code}' in country '{country_code}'.",
                        "attempts_taken": attempt,
                        "discarded_orders": discarded_orders,
                    }
                await asyncio.sleep(2.0)
                continue

            # Transient error
            if attempt >= max_attempts:
                return {
                    "success": False,
                    "error": "PURCHASE_FAILED",
                    "message": f"NexNum purchase failed: {buy.get('error', err_code)}",
                    "attempts_taken": attempt,
                    "discarded_orders": discarded_orders,
                }
            await asyncio.sleep(1.0)
            continue

        order_id = str(buy.get("order_id", ""))
        phone_number = str(buy.get("number", ""))
        cost = float(buy.get("cost", 0.0))
        clean_mobile = extract_10(phone_number)

        # Execute platform check
        try:
            check_result = await checker_fn(platform, clean_mobile)
        except Exception as exc:
            logger.error("[Purchase] Checker exception on %s (%s): %s", platform, clean_mobile, exc)
            check_result = {"status": "ERROR", "error": str(exc)}

        status = str(check_result.get("status", "UNKNOWN")).upper().strip()
        is_conclusive = status in ("REGISTERED", "NOT_REGISTERED")

        if is_conclusive:
            consecutive_inconclusive_count = 0

            if status == target_status:
                logger.info("[Purchase] Match found on attempt %d: %s (%s)", attempt, phone_number, status)
                return {
                    "success": True,
                    "order_id": order_id,
                    "phone_number": phone_number,
                    "clean_mobile": clean_mobile,
                    "platform": platform,
                    "status": status,
                    "cost": cost,
                    "attempts_taken": attempt,
                    "discarded_orders": discarded_orders,
                    "nexnum_direct_usage": {
                        "get_status_url": f"{NEXNUM_HANDLER_URL}?action=getStatus&id={order_id}&format=json",
                        "cancel_url": f"{NEXNUM_HANDLER_URL}?action=setStatus&id={order_id}&status=8&format=json",
                    },
                }

            # Conclusive mismatch — discard and retry
            logger.info("[Purchase] Mismatch on %s (expected %s, got %s) — enqueuing cancel for %s", phone_number, target_status, status, order_id)
            await cancel_queue.try_immediate_or_enqueue(key, order_id)
            discarded_orders.append({
                "order_id": order_id,
                "phone_number": phone_number,
                "status": status,
                "cancellation": "QUEUED_DEFERRED",
            })
            await asyncio.sleep(0.4)

        else:
            # Inconclusive check result (ERROR, TIMEOUT, UNKNOWN, DISABLED)
            consecutive_inconclusive_count += 1
            logger.warning(
                "[Purchase] Inconclusive check on %s (status=%s, consecutive=%d) — discarding %s",
                clean_mobile, status, consecutive_inconclusive_count, order_id
            )
            await cancel_queue.try_immediate_or_enqueue(key, order_id)
            discarded_orders.append({
                "order_id": order_id,
                "phone_number": phone_number,
                "status": status,
                "cancellation": "QUEUED_DEFERRED",
                "error": check_result.get("error") or check_result.get("message") or "Inconclusive check result",
            })

            # User requirement: If same inconclusive result occurs again consecutively, stop loop and provide error
            if consecutive_inconclusive_count >= 2:
                logger.error("[Purchase] Checker returned consecutive inconclusive results (%s) on %s. Aborting loop.", status, platform)
                return {
                    "success": False,
                    "error": "CHECKER_INCONCLUSIVE",
                    "status": status,
                    "message": f"Platform '{platform}' checker failed consecutively with status '{status}': {check_result.get('error', 'Inconclusive check')}",
                    "attempts_taken": attempt,
                    "discarded_orders": discarded_orders,
                }

            await asyncio.sleep(1.0)

    # Max attempts exhausted without a match
    return {
        "success": False,
        "error": "MAX_ATTEMPTS_EXHAUSTED",
        "message": f"Could not find a {target_status} number on {platform} after {max_attempts} attempts.",
        "attempts_taken": max_attempts,
        "discarded_orders_count": len(discarded_orders),
        "discarded_orders": discarded_orders,
    }
