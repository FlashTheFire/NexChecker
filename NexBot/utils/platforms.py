"""NexBot — Platform Registry.

Adding a new platform (e.g. Swiggy) is a 2-step process:
  1. Create core/swiggy_api.py  →  class with check_number() / startup() / shutdown() / is_ready
  2. Add a PlatformDef entry in _build_platforms() below

bot.py, callbacks.py, formatting.py, start.py all adapt automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Platform definition ───────────────────────────────────────────────────────

@dataclass
class PlatformDef:
    key:          str   # unique slug: "myntra", "bigbasket"
    label:        str   # display name: "Myntra", "BigBasket"
    icon:         str   # emoji icon: "📦", "🛒"
    flag:         str   # flag emoji: "🇮🇳"
    service_code: str   # NexNum OTP service code: "nl", "bb"
    country_code: str   # NexNum country code: "22" = India
    command:      str   # Telegram /command (no slash)
    description:  str   # short description for /help and BotCommand list
    checker:      Any   # API singleton: .check_number(mobile) / .startup() / .shutdown() / .is_ready
    needs_warmup: bool = True  # True = Playwright Chrome warmup needed at startup


# ── Registry builder (lazy — avoids circular imports at module load) ───────────

_PLATFORMS: dict[str, PlatformDef] | None = None


def _build_platforms() -> dict[str, PlatformDef]:
    from core.myntra_api import myntra_checker
    from core.bigbasket_api import bigbasket_checker
    from core.flipkart_api import flipkart_checker
    from utils.config import BB_SERVICE_CODE, FK_SERVICE_CODE

    return {
        "myntra": PlatformDef(
            key          = "myntra",
            label        = "Myntra",
            icon         = "📦",
            flag         = "🇮🇳",
            service_code = "nl",
            country_code = "22",
            command      = "myntra",
            description  = "Myntra registration checker",
            checker      = myntra_checker,
            needs_warmup = True,
        ),
        "bigbasket": PlatformDef(
            key          = "bigbasket",
            label        = "BigBasket",
            icon         = "🛒",
            flag         = "🇮🇳",
            service_code = BB_SERVICE_CODE,
            country_code = "22",
            command      = "bigbasket",
            description  = "BigBasket registration checker",
            checker      = bigbasket_checker,
            needs_warmup = False,
        ),
        "flipkart": PlatformDef(
            key          = "flipkart",
            label        = "Flipkart",
            icon         = "🛍",
            flag         = "🇮🇳",
            service_code = FK_SERVICE_CODE,
            country_code = "22",
            command      = "flipkart",
            description  = "Flipkart registration checker",
            checker      = flipkart_checker,
            needs_warmup = False,
        ),
    }


def get_platforms() -> dict[str, PlatformDef]:
    """Return the platform registry (built once, cached)."""
    global _PLATFORMS
    if _PLATFORMS is None:
        _PLATFORMS = _build_platforms()
    return _PLATFORMS


def get_platform(key: str) -> PlatformDef | None:
    """Look up a platform by key; returns None if not found."""
    return get_platforms().get(key)
