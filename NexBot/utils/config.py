"""NexBot — Global configuration constants (platform-agnostic)."""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Resolve project root & load .env ─────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# ── NexNum API ────────────────────────────────────────────────────────────────
NEXNUM_BASE_URL: str  = "https://nexnum.in/stubs/handler_api.php"

# Service codes on NexNum — configurable via .env
MYNTRA_SERVICE_CODE:    str = os.getenv("MYNTRA_SERVICE_CODE", os.getenv("SERVICE_CODE", "nl"))
SERVICE_CODE:           str = MYNTRA_SERVICE_CODE    # Legacy alias kept for backward compat
COUNTRY_CODE:           str = "22"    # India

# BigBasket service code — override via BIGBASKET_SERVICE_CODE or BB_SERVICE_CODE env var
BIGBASKET_SERVICE_CODE: str = os.getenv("BIGBASKET_SERVICE_CODE", os.getenv("BB_SERVICE_CODE", "bb"))
BB_SERVICE_CODE:        str = BIGBASKET_SERVICE_CODE

# Flipkart service code — override via FLIPKART_SERVICE_CODE or FK_SERVICE_CODE env var (default "xt")
FLIPKART_SERVICE_CODE:  str = os.getenv("FLIPKART_SERVICE_CODE", os.getenv("FK_SERVICE_CODE", "xt"))
FK_SERVICE_CODE:        str = FLIPKART_SERVICE_CODE

# ── Myntra API & Proxy ────────────────────────────────────────────────────────
PROXY:        str = os.getenv("PROXY", os.getenv("MYNTRA_PROXY", ""))
MYNTRA_PROXY: str = PROXY  # alias for backward compatibility

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR: Path = BASE_DIR / "data" / "users"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Loop behaviour ────────────────────────────────────────────────────────────
MAX_ATTEMPTS:      int   = 20    # Max loop iterations before giving up
BULK_DELAY:        float = 0.4   # Seconds between loop iterations
MIN_BALANCE:       float = 1.0   # Stop loop if user balance < this (₹)
REQUEST_TIMEOUT:   int   = 15    # aiohttp total timeout (seconds)
MAX_HEAL_RETRIES:  int   = 3     # Myntra CHALLENGE auto-heal retries
NO_NUMBERS_RETRY:  int   = 3     # Retries when NexNum returns NO_NUMBERS
NO_NUMBERS_DELAY:  float = 3.0   # Seconds to wait between NO_NUMBERS retries

# ── Cancel queue timing ───────────────────────────────────────────────────────
CANCEL_MIN_AGE:      float = 60    # Min seconds since purchase before cancel attempt
CANCEL_POLL_SECS:    int   = 30    # Background cancel-worker wake interval (seconds)
AUTO_CANCEL_TIMEOUT: int   = 10 * 60  # 10 minutes: auto-cancel order if no SMS received

