"""NexBot — Global configuration constants."""
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
SERVICE_CODE:    str  = "nl"    # Myntra service code on NexNum
COUNTRY_CODE:    str  = "22"    # India

# ── Myntra API ────────────────────────────────────────────────────────────────
MYNTRA_FORGOT_URL: str = "https://www.myntra.com/gateway/auth/v1/forgetpassword"

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
CANCEL_MIN_AGE:    float = 62.0  # Min seconds since purchase before cancel attempt
CANCEL_POLL_SECS:  int   = 30    # Background cancel-worker wake interval (seconds)
