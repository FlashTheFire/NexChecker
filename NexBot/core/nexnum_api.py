"""NexBot — NexNum API client (JSON Junction / RFC 7231 Content Negotiation).

Sends  Accept: application/json  header → NexNum returns structured JSON.

REAL JSON shapes (verified live):
  getBalance  → { "status": "success",       "balance": 12604.37, "display": "12604.37" }
  getNumber   → { "status": "success",       "activationId": "...", "phoneNumber": "...",
                                              "cost": 9, "country": 22, "service": 2426 }
  getStatus   → { "status": "STATUS_WAIT_CODE", "activationId": "...", "code": "", "sms": [] }
                { "status": "STATUS_OK",         "code": "123456", "sms": [...] }
                { "status": "ACCESS_CANCEL" }
  setStatus 8 → { "status": "error", "code": "EARLY_CANCEL_DENIED", "message": "..." }
                                    (too soon — bot defers to background cancel queue)
                { "status": "ACCESS_CANCEL" }   (cancel accepted)
  Errors      → { "status": "error", "code": "BAD_KEY" | "NO_BALANCE" | "NO_NUMBERS" | ... }

Wire-format fallback: if JSON decode fails, splits plain text  ACCESS_NUMBER:id:num  etc.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from utils.config import NEXNUM_BASE_URL, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


# ── Status string constants ───────────────────────────────────────────────────
class NexNumStatus:
    # Success tokens
    SUCCESS        = "success"
    STATUS_OK      = "STATUS_OK"
    STATUS_WAIT    = "STATUS_WAIT_CODE"
    ACCESS_CANCEL  = "ACCESS_CANCEL"
    STATUS_CANCEL  = "STATUS_CANCEL"
    # Error tokens (in "code" field when status == "error")
    BAD_KEY        = "BAD_KEY"
    NO_BALANCE     = "NO_BALANCE"
    NO_NUMBERS     = "NO_NUMBERS"
    BANNED         = "BANNED"
    EARLY_CANCEL   = "EARLY_CANCEL_DENIED"   # cancel too soon → defer
    BAD_STATUS     = "BAD_STATUS"            # Order in final state: OTP received / already cancelled / completed
    # Internal
    ERROR          = "ERROR"
    UNKNOWN        = "UNKNOWN"

    # Terminal cancel errors — order is in a final state, cancel will never succeed
    # BAD_STATUS = OTP received OR order already cancelled OR order completed
    CANCEL_TERMINAL = {"BAD_STATUS", "BAD_KEY", "BANNED", "ACCESS_ACTIVATION"}


# ── Wire-format fallback parser ───────────────────────────────────────────────

def _parse_wire(text: str) -> Dict[str, Any]:
    """Parse legacy plain-wire format as a safety fallback."""
    text  = text.strip()
    parts = text.split(":", 2)
    raw   = parts[0] if parts else NexNumStatus.ERROR

    # Map wire tokens → internal format
    if raw == "ACCESS_NUMBER" and len(parts) >= 3:
        return {"status": "success", "activationId": parts[1], "phoneNumber": parts[2]}
    if raw == "ACCESS_BALANCE" and len(parts) >= 2:
        try:
            return {"status": "success", "balance": float(parts[1])}
        except ValueError:
            pass
    if raw == "STATUS_OK":
        return {"status": "STATUS_OK", "code": parts[1] if len(parts) >= 2 else ""}
    if raw == "ACCESS_CANCEL":
        return {"status": "ACCESS_CANCEL"}
    if raw in ("BAD_KEY", "NO_BALANCE", "NO_NUMBERS", "BANNED"):
        return {"status": "error", "code": raw}
    return {"status": "error", "code": raw, "_wire": text}


# ── Client ────────────────────────────────────────────────────────────────────

class NexNumClient:
    """Async NexNum API client — JSON Junction (Accept: application/json)."""

    _HEADERS: Dict[str, str] = {
        "Accept":     "application/json",
        "User-Agent": "NexChecker-Bot/2.0",
    }

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._HEADERS,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Raw request with retries ──────────────────────────────────────────────

    async def _get(self, params: Dict[str, str]) -> Dict[str, Any]:
        """GET → JSON dict.  Falls back to wire parser.  Retries 3× with backoff."""
        session = await self._sess()

        for attempt in range(3):
            try:
                async with session.get(NEXNUM_BASE_URL, params=params) as resp:
                    body = await resp.text()
                    logger.debug("[NexNum] %s → %s", params.get("action"), body[:200])

                    try:
                        data = await resp.json(content_type=None)
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass

                    return _parse_wire(body)   # fallback

            except asyncio.TimeoutError:
                logger.warning("[NexNum] timeout attempt %d/3", attempt + 1)
                if attempt == 2:
                    return {"status": "error", "code": "TIMEOUT"}
                await asyncio.sleep(1.5 ** attempt)

            except aiohttp.ClientError as exc:
                logger.warning("[NexNum] client error attempt %d/3: %s", attempt + 1, exc)
                if attempt == 2:
                    return {"status": "error", "code": "CLIENT_ERROR", "message": str(exc)}
                await asyncio.sleep(1.0)

        return {"status": "error", "code": "MAX_RETRIES"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_error(data: Dict[str, Any]) -> bool:
        return data.get("status") == "error"

    @staticmethod
    def _error_code(data: Dict[str, Any]) -> str:
        return str(data.get("code", data.get("status", "UNKNOWN")))

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_balance(self, api_key: str) -> Dict[str, Any]:
        """
        JSON: ``{ "status": "success", "balance": 12604.37, "display": "12604.37" }``
        Returns: ``{ "ok": bool, "balance": float, "error": str | None }``
        """
        data = await self._get({"api_key": api_key, "action": "getBalance"})

        if data.get("status") == "success":
            try:
                balance = float(data.get("balance", 0))
            except (TypeError, ValueError):
                balance = 0.0
            return {"ok": True, "balance": balance, "error": None}

        code = self._error_code(data)
        return {"ok": False, "balance": 0.0, "error": code}

    async def get_number(
        self, api_key: str, service: str, country: str
    ) -> Dict[str, Any]:
        """
        JSON: ``{ "status": "success", "activationId": "...", "phoneNumber": "...",
                  "cost": 9, "country": 22, "service": 2426 }``
        Returns on success:
            ``{ "ok": True, "order_id": str, "number": str, "cost": int }``
        Returns on failure:
            ``{ "ok": False, "status": str, "error": str }``
        """
        data = await self._get({
            "api_key": api_key,
            "action":  "getNumber",
            "service": service,
            "country": country,
        })

        if data.get("status") == "success":
            order_id = str(data.get("activationId", ""))
            number   = str(data.get("phoneNumber",  ""))
            if order_id and number:
                return {
                    "ok":       True,
                    "status":   NexNumStatus.SUCCESS,
                    "order_id": order_id,
                    "number":   number,
                    "cost":     data.get("cost", 0),
                }

        code = self._error_code(data)
        # Map JSON error codes → NexNumStatus constants used by the handler
        status_map = {
            "NO_BALANCE":  NexNumStatus.NO_BALANCE,
            "BAD_KEY":     NexNumStatus.BAD_KEY,
            "NO_NUMBERS":  NexNumStatus.NO_NUMBERS,
            "BANNED":      NexNumStatus.BANNED,
        }
        return {
            "ok":     False,
            "status": status_map.get(code, NexNumStatus.ERROR),
            "error":  data.get("message", code),
        }

    async def get_status(self, api_key: str, order_id: str) -> Dict[str, Any]:
        """
        JSON: ``{ "status": "STATUS_WAIT_CODE", "code": "", "sms": [] }``
              ``{ "status": "STATUS_OK", "code": "123456", "sms": [...] }``
              ``{ "status": "ACCESS_CANCEL" }``
        Returns: ``{ "ok": bool, "status": str, "code": str, "sms": list }``
        """
        data   = await self._get({"api_key": api_key, "action": "getStatus", "id": order_id})
        status = data.get("status", NexNumStatus.ERROR)
        code   = str(data.get("code", ""))
        sms:  List[Any] = data.get("sms", [])

        # fullSms / sender — may be at top level OR inside sms[0]
        full_sms = str(data.get("fullSms", "")).strip()
        sender   = str(data.get("sender",  "")).strip()
        if not full_sms and sms:
            full_sms = str(sms[0].get("text",   "")).strip()
        if not sender and sms:
            sender   = str(sms[0].get("sender", "")).strip()

        ok = status not in ("error", NexNumStatus.ERROR)
        return {
            "ok":       ok,
            "status":   status,
            "code":     code,
            "sms":      sms,
            "full_sms": full_sms,
            "sender":   sender,
            "order_id": order_id,
            "error":    self._error_code(data) if not ok else None,
        }

    async def set_status(
        self, api_key: str, order_id: str, status: int
    ) -> Dict[str, Any]:
        """
        JSON success: ``{ "status": "ACCESS_CANCEL" }``
        JSON too-soon: ``{ "status": "error", "code": "EARLY_CANCEL_DENIED", ... }``
        Returns: ``{ "ok": bool, "status": str, "early_denied": bool }``
        """
        data       = await self._get({
            "api_key": api_key,
            "action":  "setStatus",
            "id":      order_id,
            "status":  str(status),
        })
        status_str = data.get("status", "error")
        code       = self._error_code(data)

        ok = status_str in (
            NexNumStatus.ACCESS_CANCEL,
            NexNumStatus.STATUS_CANCEL,
            NexNumStatus.SUCCESS,   # NexNum sometimes returns "success" for cancel ack
        )
        early_denied  = code == NexNumStatus.EARLY_CANCEL

        return {
            "ok":           ok,
            "status":       status_str,
            "code":         code,
            "early_denied": early_denied,
            "error":        None if ok else data.get("message", code),
        }


# ── Module-level singleton ────────────────────────────────────────────────────
nexnum_client = NexNumClient()
