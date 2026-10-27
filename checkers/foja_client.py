"""
FojaClient - High-Performance Client for PriceTrackerPro / Foja API
====================================================================
Production client providing synchronous and asynchronous access to all
endpoints on https://pricetrackerpro.fojadomain.fun/api/

Supported Features:
  1. Registration & Freshness Checker (Single & Bulk)
  2. Account Management (List, Select, Delete, Refresh, Export, Import)
  3. Address Management (Get User Address, Meesho Address Book, Bind Order)
  4. Cart Operations (Inspect, Add, Remove, Update Qty, Checkout)
  5. Checkout & Payments (Summary, COD, UPI QR, Juspay Status Polling, Cancel)
  6. Orders Management (List Orders, Global Orders, Cancel Order)
  7. Search & Catalog (Search, Suggest, Product Details by ID/Link)
  8. Referral & Session (Stats, Save Referral, Session Bootstrap, Pending Tasks)
  9. Login / OTP Flow (Start, Send OTP, Verify OTP, Progress Polling)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger("foja_client")

DEFAULT_BASE_URL = "https://pricetrackerpro.fojadomain.fun"
DEFAULT_TOKEN = "1889471360.532228cbff3c2dcf"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)


# ============================================================================
# Data Models
# ============================================================================

def clean_phone(raw: str) -> str:
    """Normalize phone number to 10 digits."""
    digits = re.sub(r"\D", "", str(raw))
    return digits[-10:] if len(digits) >= 10 else digits


@dataclass
class CheckResult:
    number: str
    registered: bool
    fresh: bool
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> CheckResult:
        return cls(
            number=str(data.get("number", "")),
            registered=bool(data.get("registered", False)),
            fresh=bool(data.get("fresh", not data.get("registered", False))),
            raw=data,
        )


@dataclass
class BatchCheckResponse:
    ok: bool
    results: List[CheckResult]
    total: int
    fresh: int
    registered: int
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> BatchCheckResponse:
        results = [CheckResult.from_dict(r) for r in data.get("results", [])]
        return cls(
            ok=bool(data.get("ok", False)),
            results=results,
            total=int(data.get("total", len(results))),
            fresh=int(data.get("fresh", sum(1 for r in results if r.fresh))),
            registered=int(data.get("registered", sum(1 for r in results if r.registered))),
            raw=data,
        )


@dataclass
class AddressInfo:
    name: str = ""
    mobile: str = ""
    pin: str = ""
    city: str = ""
    state: str = ""
    line1: str = ""
    line2: str = ""
    referral: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> AddressInfo:
        addr = data.get("address") or {}
        return cls(
            name=addr.get("name", ""),
            mobile=addr.get("mobile", ""),
            pin=addr.get("pin", ""),
            city=addr.get("city", ""),
            state=addr.get("state", ""),
            line1=addr.get("line1", ""),
            line2=addr.get("line2", ""),
            referral=str(data.get("referral", "")),
            raw=data,
        )


@dataclass
class SessionInfo:
    ok: bool
    slots: int = 0
    accounts: int = 0
    fresh: int = 0
    orders: int = 0
    has_address: bool = False
    first_name: str = ""
    cart_phone: str = ""
    cart_count: int = 0
    my_referral: str = ""
    last_phone: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> SessionInfo:
        return cls(
            ok=bool(data.get("ok", False)),
            slots=int(data.get("slots", 0)),
            accounts=int(data.get("accounts", 0)),
            fresh=int(data.get("fresh", 0)),
            orders=int(data.get("orders", 0)),
            has_address=bool(data.get("has_address", False)),
            first_name=str(data.get("first_name", "")),
            cart_phone=str(data.get("cart_phone", "")),
            cart_count=int(data.get("cart_count", 0)),
            my_referral=str(data.get("my_referral", "")),
            last_phone=str(data.get("last_phone", "")),
            raw=data,
        )


@dataclass
class AccountSummary:
    phone: str
    user_id: str
    best_fod: float = 0.0
    placed: bool = False
    order_num: str = ""
    order_status: str = ""
    saved_at: str = ""
    new_account: bool = False
    export_unlocked: bool = False
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> AccountSummary:
        return cls(
            phone=str(data.get("phone", "")),
            user_id=str(data.get("user_id", "")),
            best_fod=float(data.get("best_fod", 0.0)),
            placed=bool(data.get("placed", False)),
            order_num=str(data.get("order_num", "")),
            order_status=str(data.get("order_status", "")),
            saved_at=str(data.get("saved_at", "")),
            new_account=bool(data.get("new_account", False)),
            export_unlocked=bool(data.get("export_unlocked", False)),
            raw=data,
        )


@dataclass
class OrderItem:
    order_num: str
    status: str
    phone: str
    product: str
    amount: str = ""
    image: str = ""
    date: str = ""
    created: int = 0
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> OrderItem:
        return cls(
            order_num=str(data.get("order_num", "")),
            status=str(data.get("status", "")),
            phone=str(data.get("phone", "")),
            product=str(data.get("product", "")),
            amount=str(data.get("amount", "")),
            image=str(data.get("image", "")),
            date=str(data.get("date", "")),
            created=int(data.get("created", 0)),
            raw=data,
        )


@dataclass
class CartItem:
    id: str
    product_id: int
    name: str
    variation: str = ""
    cod: float = 0.0
    mrp: float = 0.0
    quantity: int = 1
    max_quantity: int = 10
    image: str = ""
    supplier: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> CartItem:
        return cls(
            id=str(data.get("id", "")),
            product_id=int(data.get("product_id", 0)),
            name=str(data.get("name", "")),
            variation=str(data.get("variation", "")),
            cod=float(data.get("cod", 0.0)),
            mrp=float(data.get("mrp", 0.0)),
            quantity=int(data.get("quantity", 1)),
            max_quantity=int(data.get("max_quantity", 10)),
            image=str(data.get("image", "")),
            supplier=str(data.get("supplier", "")),
            raw=data,
        )


@dataclass
class CartInfo:
    ok: bool
    phone: str
    count: int
    total: float
    items: List[CartItem]
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> CartInfo:
        items = [CartItem.from_dict(i) for i in data.get("items", [])]
        return cls(
            ok=bool(data.get("ok", False)),
            phone=str(data.get("phone", "")),
            count=int(data.get("count", len(items))),
            total=float(data.get("total", 0.0)),
            items=items,
            raw=data,
        )


# ============================================================================
# Main FojaClient Class
# ============================================================================

class FojaClient:
    """
    Universal Client for PriceTrackerPro / Foja Meesho Platform.

    Supports both Async (via `async with FojaClient()`) and
    Sync (via standard methods on the instance).
    """

    def __init__(
        self,
        token: str = DEFAULT_TOKEN,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_UA,
        timeout: float = 25.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.user_agent = user_agent
        self.timeout = timeout
        self._async_client: Optional[httpx.AsyncClient] = None
        self._sync_client: Optional[httpx.Client] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
            "user-agent": self.user_agent,
            "x-token": self.token,
        }

    # ─── Context Managers ─────────────────────────────────────────────────────

    async def __aenter__(self) -> FojaClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self) -> FojaClient:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self

    def __exit__(self, *args: Any) -> None:
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    # ─── Internal Request Helpers ─────────────────────────────────────────────

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._async_client

    async def _async_request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        client = self._get_async_client()
        p = dict(params or {})
        p["_"] = int(time.time() * 1000)

        resp = await client.request(
            method=method,
            url=path,
            params=p,
            json=body if body is not None else None,
        )
        resp.raise_for_status()
        return resp.json() or {}

    def _sync_request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        client = self._get_sync_client()
        p = dict(params or {})
        p["_"] = int(time.time() * 1000)

        resp = client.request(
            method=method,
            url=path,
            params=p,
            json=body if body is not None else None,
        )
        resp.raise_for_status()
        return resp.json() or {}

    # =========================================================================
    # 1. Registration & Freshness Checker
    # =========================================================================

    async def check_number_async(self, phone: str) -> CheckResult:
        """
        Check if a single Indian mobile number is registered on Meesho.
        No SMS/OTP sent. Authoritative verdict.
        """
        mobile = clean_phone(phone)
        data = await self._async_request("POST", "/api/check", body={"number": mobile})
        results = data.get("results") or []
        if results:
            return CheckResult.from_dict(results[0])
        return CheckResult(number=f"+91{mobile}", registered=False, fresh=True, raw=data)

    def check_number(self, phone: str) -> CheckResult:
        """Synchronous version of check_number_async."""
        mobile = clean_phone(phone)
        data = self._sync_request("POST", "/api/check", body={"number": mobile})
        results = data.get("results") or []
        if results:
            return CheckResult.from_dict(results[0])
        return CheckResult(number=f"+91{mobile}", registered=False, fresh=True, raw=data)

    async def check_numbers_async(self, phones: List[str]) -> BatchCheckResponse:
        """Bulk check a list of Indian mobile numbers."""
        cleaned = [clean_phone(p) for p in phones]
        data = await self._async_request("POST", "/api/check", body={"numbers": cleaned})
        return BatchCheckResponse.from_dict(data)

    def check_numbers(self, phones: List[str]) -> BatchCheckResponse:
        """Synchronous version of check_numbers_async."""
        cleaned = [clean_phone(p) for p in phones]
        data = self._sync_request("POST", "/api/check", body={"numbers": cleaned})
        return BatchCheckResponse.from_dict(data)

    # =========================================================================
    # 2. Session & Status
    # =========================================================================

    async def get_session_async(
        self,
        platform: str = "Win32",
        timezone: str = "Asia/Calcutta",
    ) -> SessionInfo:
        """Fetch active session metadata, slot counts, cart counts, and referral code."""
        params = {
            "ua": self.user_agent,
            "pf": platform,
            "lg": "en-IN",
            "tz": timezone,
            "sc": "1536x864x1.25",
        }
        data = await self._async_request("GET", "/api/session", params=params)
        return SessionInfo.from_dict(data)

    def get_session(
        self,
        platform: str = "Win32",
        timezone: str = "Asia/Calcutta",
    ) -> SessionInfo:
        """Synchronous version of get_session_async."""
        params = {
            "ua": self.user_agent,
            "pf": platform,
            "lg": "en-IN",
            "tz": timezone,
            "sc": "1536x864x1.25",
        }
        data = self._sync_request("GET", "/api/session", params=params)
        return SessionInfo.from_dict(data)

    async def get_pending_async(self) -> List[dict]:
        """Fetch pending queue tasks."""
        data = await self._async_request("GET", "/api/pending")
        return data.get("pending", [])

    def get_pending(self) -> List[dict]:
        """Synchronous version of get_pending_async."""
        data = self._sync_request("GET", "/api/pending")
        return data.get("pending", [])

    # =========================================================================
    # 3. Account Management
    # =========================================================================

    async def get_accounts_async(self) -> List[AccountSummary]:
        """Fetch all accounts currently registered in the wallet."""
        data = await self._async_request("GET", "/api/accounts")
        return [AccountSummary.from_dict(acc) for acc in data.get("accounts", [])]

    def get_accounts(self) -> List[AccountSummary]:
        """Synchronous version of get_accounts_async."""
        data = self._sync_request("GET", "/api/accounts")
        return [AccountSummary.from_dict(acc) for acc in data.get("accounts", [])]

    async def refresh_accounts_async(self, offset: int = 0) -> dict:
        """Trigger background batch refresh of account sessions."""
        return await self._async_request("POST", "/api/accounts/refresh", body={"offset": offset})

    def refresh_accounts(self, offset: int = 0) -> dict:
        """Synchronous version of refresh_accounts_async."""
        return self._sync_request("POST", "/api/accounts/refresh", body={"offset": offset})

    async def refresh_account_async(self, phone: str) -> dict:
        """Refresh orders and FOD status for a specific account."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("POST", "/api/account/refresh", body={"phone": p})

    def refresh_account(self, phone: str) -> dict:
        """Synchronous version of refresh_account_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("POST", "/api/account/refresh", body={"phone": p})

    async def select_account_async(self, phone: str) -> dict:
        """Select an account as active in the wallet session."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("POST", "/api/account/select", body={"phone": p})

    def select_account(self, phone: str) -> dict:
        """Synchronous version of select_account_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("POST", "/api/account/select", body={"phone": p})

    async def delete_account_async(self, phone: str) -> dict:
        """Delete an account from the wallet."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("POST", "/api/account/delete", body={"phone": p})

    def delete_account(self, phone: str) -> dict:
        """Synchronous version of delete_account_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("POST", "/api/account/delete", body={"phone": p})

    async def export_account_async(self, phone: str) -> dict:
        """Export session JSON for an account."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("GET", "/api/export", params={"phone": p})

    def export_account(self, phone: str) -> dict:
        """Synchronous version of export_account_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("GET", "/api/export", params={"phone": p})

    async def unlock_export_async(self, phone: str) -> dict:
        """Unlock export for an account using 1 slot."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("POST", "/api/export/unlock", body={"phone": p})

    def unlock_export(self, phone: str) -> dict:
        """Synchronous version of unlock_export_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("POST", "/api/export/unlock", body={"phone": p})

    async def import_account_async(self, account_data: dict) -> dict:
        """Import an account session JSON bundle."""
        return await self._async_request("POST", "/api/import", body={"data": account_data})

    def import_account(self, account_data: dict) -> dict:
        """Synchronous version of import_account_async."""
        return self._sync_request("POST", "/api/import", body={"data": account_data})

    # =========================================================================
    # 4. Address Management
    # =========================================================================

    async def get_address_async(self) -> AddressInfo:
        """Get the user's default saved delivery address."""
        data = await self._async_request("GET", "/api/address")
        return AddressInfo.from_dict(data)

    def get_address(self) -> AddressInfo:
        """Synchronous version of get_address_async."""
        data = self._sync_request("GET", "/api/address")
        return AddressInfo.from_dict(data)

    async def save_address_async(self, address_dict: dict) -> dict:
        """Save/update the user default address."""
        return await self._async_request("POST", "/api/address/save", body=address_dict)

    def save_address(self, address_dict: dict) -> dict:
        """Synchronous version of save_address_async."""
        return self._sync_request("POST", "/api/address/save", body=address_dict)

    async def get_meesho_addresses_async(self, phone: str) -> List[dict]:
        """Fetch all addresses currently stored directly on Meesho for an account."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = await self._async_request("POST", "/api/meesho/addresses", body={"phone": p})
        return data.get("addresses", [])

    def get_meesho_addresses(self, phone: str) -> List[dict]:
        """Synchronous version of get_meesho_addresses_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = self._sync_request("POST", "/api/meesho/addresses", body={"phone": p})
        return data.get("addresses", [])

    # =========================================================================
    # 5. Orders Management
    # =========================================================================

    async def get_orders_async(self, phone: str) -> List[OrderItem]:
        """Fetch orders for a specific phone number."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = await self._async_request("GET", "/api/orders", params={"phone": p})
        return [OrderItem.from_dict(o) for o in data.get("orders", [])]

    def get_orders(self, phone: str) -> List[OrderItem]:
        """Synchronous version of get_orders_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = self._sync_request("GET", "/api/orders", params={"phone": p})
        return [OrderItem.from_dict(o) for o in data.get("orders", [])]

    async def get_all_orders_async(self, offset: int = 0) -> List[OrderItem]:
        """Fetch all orders across all accounts in wallet."""
        data = await self._async_request("GET", "/api/orders/all", params={"offset": offset})
        return [OrderItem.from_dict(o) for o in data.get("orders", [])]

    def get_all_orders(self, offset: int = 0) -> List[OrderItem]:
        """Synchronous version of get_all_orders_async."""
        data = self._sync_request("GET", "/api/orders/all", params={"offset": offset})
        return [OrderItem.from_dict(o) for o in data.get("orders", [])]

    async def get_order_detail_async(self, order_num: str, phone: Optional[str] = None) -> dict:
        """Fetch full details and tracking timeline for a specific order."""
        params = {}
        if phone:
            params["phone"] = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return await self._async_request("GET", f"/api/orders/{order_num}", params=params)

    def get_order_detail(self, order_num: str, phone: Optional[str] = None) -> dict:
        """Synchronous version of get_order_detail_async."""
        params = {}
        if phone:
            params["phone"] = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        return self._sync_request("GET", f"/api/orders/{order_num}", params=params)

    async def cancel_order_async(
        self,
        phone: str,
        order_num: str,
        reason_id: str,
        comment: str = "",
    ) -> dict:
        """Cancel an active order on Meesho."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {
            "phone": p,
            "order_num": order_num,
            "reason_id": reason_id,
            "comment": comment,
        }
        return await self._async_request("POST", "/api/order/cancel", body=body)

    def cancel_order(
        self,
        phone: str,
        order_num: str,
        reason_id: str,
        comment: str = "",
    ) -> dict:
        """Synchronous version of cancel_order_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {
            "phone": p,
            "order_num": order_num,
            "reason_id": reason_id,
            "comment": comment,
        }
        return self._sync_request("POST", "/api/order/cancel", body=body)

    # =========================================================================
    # 6. Cart Management
    # =========================================================================

    async def get_cart_async(self, phone: str) -> CartInfo:
        """Fetch cart contents and total for an account."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = await self._async_request("POST", "/api/cart", body={"phone": p})
        return CartInfo.from_dict(data)

    def get_cart(self, phone: str) -> CartInfo:
        """Synchronous version of get_cart_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        data = self._sync_request("POST", "/api/cart", body={"phone": p})
        return CartInfo.from_dict(data)

    async def add_to_cart_async(
        self,
        phone: str,
        variation: str,
        quantity: int = 1,
    ) -> dict:
        """Add an item variation to cart."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "variation": variation, "quantity": quantity}
        return await self._async_request("POST", "/api/cart/add", body=body)

    def add_to_cart(
        self,
        phone: str,
        variation: str,
        quantity: int = 1,
    ) -> dict:
        """Synchronous version of add_to_cart_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "variation": variation, "quantity": quantity}
        return self._sync_request("POST", "/api/cart/add", body=body)

    async def update_cart_qty_async(
        self,
        phone: str,
        item_id: str,
        delta: int,
    ) -> dict:
        """Increase or decrease cart item quantity."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "id": item_id, "delta": delta}
        return await self._async_request("POST", "/api/cart/qty", body=body)

    def update_cart_qty(
        self,
        phone: str,
        item_id: str,
        delta: int,
    ) -> dict:
        """Synchronous version of update_cart_qty_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "id": item_id, "delta": delta}
        return self._sync_request("POST", "/api/cart/qty", body=body)

    async def remove_from_cart_async(self, phone: str, item_id: str) -> dict:
        """Remove an item from cart."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "id": item_id}
        return await self._async_request("POST", "/api/cart/remove", body=body)

    def remove_from_cart(self, phone: str, item_id: str) -> dict:
        """Synchronous version of remove_from_cart_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "id": item_id}
        return self._sync_request("POST", "/api/cart/remove", body=body)

    # =========================================================================
    # 7. Checkout & Payments
    # =========================================================================

    async def get_checkout_summary_async(self, phone: str, variation: str) -> dict:
        """Get pre-checkout summary and price breakdown."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "variation": variation}
        return await self._async_request("POST", "/api/checkout/summary", body=body)

    def get_checkout_summary(self, phone: str, variation: str) -> dict:
        """Synchronous version of get_checkout_summary_async."""
        p = f"+91{clean_phone(phone)}" if not phone.startswith("+") else phone
        body = {"phone": p, "variation": variation}
        return self._sync_request("POST", "/api/checkout/summary", body=body)

    async def checkout_cod_async(self) -> dict:
        """Place order via Cash On Delivery."""
        return await self._async_request("POST", "/api/checkout/cod", body={})

    def checkout_cod(self) -> dict:
        """Synchronous version of checkout_cod_async."""
        return self._sync_request("POST", "/api/checkout/cod", body={})

    async def checkout_upi_async(self) -> dict:
        """Initialize UPI QR order via Juspay."""
        return await self._async_request("POST", "/api/checkout/upi", body={})

    def checkout_upi(self) -> dict:
        """Synchronous version of checkout_upi_async."""
        return self._sync_request("POST", "/api/checkout/upi", body={})

    async def check_upi_payment_async(self, juspay_order_id: str) -> dict:
        """Poll UPI payment status."""
        return await self._async_request(
            "POST", "/api/checkout/check", body={"juspay_order_id": juspay_order_id}
        )

    def check_upi_payment(self, juspay_order_id: str) -> dict:
        """Synchronous version of check_upi_payment_async."""
        return self._sync_request(
            "POST", "/api/checkout/check", body={"juspay_order_id": juspay_order_id}
        )

    async def cancel_upi_payment_async(self, juspay_order_id: str) -> dict:
        """Cancel an in-flight UPI payment intent."""
        return await self._async_request(
            "POST", "/api/checkout/cancel", body={"juspay_order_id": juspay_order_id}
        )

    def cancel_upi_payment(self, juspay_order_id: str) -> dict:
        """Synchronous version of cancel_upi_payment_async."""
        return self._sync_request(
            "POST", "/api/checkout/cancel", body={"juspay_order_id": juspay_order_id}
        )

    async def discard_checkout_async(self, soft: bool = False) -> dict:
        """Discard the active checkout session."""
        return await self._async_request(
            "POST", "/api/checkout/discard", body={"soft": soft}
        )

    def discard_checkout(self, soft: bool = False) -> dict:
        """Synchronous version of discard_checkout_async."""
        return self._sync_request(
            "POST", "/api/checkout/discard", body={"soft": soft}
        )

    # =========================================================================
    # 8. Search & Catalog
    # =========================================================================

    async def search_async(self, query: str, phone: str = "") -> dict:
        """Search Meesho product catalog."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return await self._async_request("POST", "/api/search", body={"phone": p, "q": query})

    def search(self, query: str, phone: str = "") -> dict:
        """Synchronous version of search_async."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return self._sync_request("POST", "/api/search", body={"phone": p, "q": query})

    async def search_suggest_async(self, query: str, phone: str = "") -> dict:
        """Get live autocomplete suggestions."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return await self._async_request(
            "POST", "/api/search/suggest", body={"phone": p, "q": query.strip()}
        )

    def search_suggest(self, query: str, phone: str = "") -> dict:
        """Synchronous version of search_suggest_async."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return self._sync_request(
            "POST", "/api/search/suggest", body={"phone": p, "q": query.strip()}
        )

    async def get_product_async(self, pid: Union[int, str], phone: str = "") -> dict:
        """Get full details for a product by Meesho product ID."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return await self._async_request(
            "POST", "/api/search/product", body={"phone": p, "pid": str(pid)}
        )

    def get_product(self, pid: Union[int, str], phone: str = "") -> dict:
        """Synchronous version of get_product_async."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return self._sync_request(
            "POST", "/api/search/product", body={"phone": p, "pid": str(pid)}
        )

    async def resolve_product_link_async(self, link: str, phone: str = "") -> dict:
        """Resolve a product from a shared Meesho URL."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return await self._async_request(
            "POST", "/api/product", body={"phone": p, "link": link}
        )

    def resolve_product_link(self, link: str, phone: str = "") -> dict:
        """Synchronous version of resolve_product_link_async."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return self._sync_request(
            "POST", "/api/product", body={"phone": p, "link": link}
        )

    # =========================================================================
    # 9. Referral & Wallet Stats
    # =========================================================================

    async def get_referral_stats_async(self, phone: str = "") -> dict:
        """Get referral rewards and link statistics."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return await self._async_request("POST", "/api/referral/stats", body={"phone": p})

    def get_referral_stats(self, phone: str = "") -> dict:
        """Synchronous version of get_referral_stats_async."""
        p = f"+91{clean_phone(phone)}" if phone else ""
        return self._sync_request("POST", "/api/referral/stats", body={"phone": p})

    async def save_referral_async(self, referral_code: str) -> dict:
        """Save active referral code."""
        return await self._async_request(
            "POST", "/api/referral/save", body={"referral": referral_code}
        )

    def save_referral(self, referral_code: str) -> dict:
        """Synchronous version of save_referral_async."""
        return self._sync_request(
            "POST", "/api/referral/save", body={"referral": referral_code}
        )
