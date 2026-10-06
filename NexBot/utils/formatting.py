"""NexBot — Text formatting helpers.

All card builders accept an optional ``platform`` argument (a PlatformDef).
When omitted (or None), they fall back to Myntra defaults so existing call
sites that haven't been updated yet continue to work unchanged.
"""
from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.platforms import PlatformDef

# ── Unicode small-caps map ────────────────────────────────────────────────────
_SC: dict[str, str] = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ғ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "Q", "r": "ʀ",
    "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}


def small_caps(text: str) -> str:
    """Convert all lowercase ASCII letters to Unicode small-caps glyphs."""
    return "".join(_SC.get(c, c) for c in text)


def sc(text: str) -> str:
    """Shorthand alias for small_caps()."""
    return small_caps(text)


def blockquote(text: str) -> str:
    """Wrap text in a Telegram HTML blockquote element."""
    return f"<blockquote>{text}</blockquote>"


def code(text: str) -> str:
    return f"<code>{text}</code>"


def bold(text: str) -> str:
    return f"<b>{text}</b>"


# ── Platform helpers ──────────────────────────────────────────────────────────

def _plat_label(platform: "PlatformDef | None") -> str:
    return platform.label if platform else "Myntra"

def _plat_icon(platform: "PlatformDef | None") -> str:
    return platform.icon if platform else "📦"

def _plat_flag(platform: "PlatformDef | None") -> str:
    return platform.flag if platform else "🇮🇳"


# ── Phone formatting ──────────────────────────────────────────────────────────

def format_phone(number: str | int) -> str:
    """Format to +91 XXXXX XXXXX."""
    digits = "".join(c for c in str(number) if c.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]
    if len(digits) == 10:
        return f"+91 {digits[:5]} {digits[5:]}"
    return f"+{digits}"


def extract_10(number: str | int) -> str:
    """Return the last 10 digits (strips country prefix)."""
    digits = "".join(c for c in str(number) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _split_phone(number: str | int):
    """Return (cc, national) tuple for split display: +91 / 9693244147."""
    digits = extract_10(number)
    return "+91", digits


# ── Balance formatting ────────────────────────────────────────────────────────

def format_balance(balance: float) -> str:
    return f"₹{balance:.2f}"


# ── Timestamp ─────────────────────────────────────────────────────────────────

def now_time() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


# ── Structured message builders ───────────────────────────────────────────────

def build_result_card(
    number:   str | int,
    status:   str,
    order_id: str,
    attempt:  int,
    cost:     int | float,
    otp_code: str | None = None,
    platform: "PlatformDef | None" = None,
) -> str:
    """NexNum bot style result card.

    <blockquote><b>📦 Mʏɴᴛʀᴀ [</b> 💎 9.00 <b>][ 🇮🇳 ]</b></blockquote>

    📱 <b>Nᴜᴍʙᴇʀ »</b> <code>+91</code> <code>82524 48734</code>

    ✅  <b>Sᴛᴀᴛᴜꜱ ɪꜱ Rᴇɢɪꜱᴛᴇʀᴇᴅ!</b>
    """
    cc, nat = _split_phone(number)

    label    = sc(_plat_label(platform))
    icon     = _plat_icon(platform)
    flag     = _plat_flag(platform)

    if status == "REGISTERED":
        stat_icon   = "✅"
        status_text = sc("Status Is Registered")
    elif status == "NOT_REGISTERED":
        stat_icon   = "🛑"
        status_text = sc("Status Is Not Registered")
    else:
        stat_icon   = "⚠️"
        status_text = sc("Status Unknown")

    cost_str = f"{float(cost):.2f}"

    otp_line = ""
    if otp_code:
        otp_line = f"\n\n🔐 <b>{sc('Otp Code')} »</b>  <code>{otp_code}</code>"
    else:
        otp_line = f"\n\n⏳  <b>{sc('Waiting For Sms…')}</b>"

    return (
        f"<blockquote><b>{icon} {label} [</b> 💎 {cost_str} <b>][ {flag} ]</b></blockquote>\n\n"
        f"📱 <b>{sc('Number')} »</b> <code>{cc}</code> <code>{nat}</code>"
        f"{otp_line}\n\n"
        f"{stat_icon}  <b>{status_text}!</b>"
    )


def build_progress_msg(
    attempt:     int,
    phase:       str,
    filter_mode: str,
    number:      str = "",
    platform:    "PlatformDef | None" = None,
) -> str:
    """Live progress card — blockquote header matching the result card style."""
    label = sc(_plat_label(platform))
    flag  = _plat_flag(platform)
    icon  = _plat_icon(platform)

    filter_labels = {
        "REGISTERED":     f"✅ {sc('Registered')}",
        "NOT_REGISTERED": f"🛑 {sc('Not Registered')}",
        "ANY":            f"📊 {sc('Any')}",
    }
    f_label = filter_labels.get(filter_mode, filter_mode)

    number_line = ""
    if number:
        cc, nat = _split_phone(number)
        number_line = f"\n📱 <b>{sc('Number')} »</b> <code>{cc}</code> <code>{nat}</code>"

    return (
        f"<blockquote><b>{icon} {label} [</b> {flag} <b>][</b> {f_label} <b>]</b></blockquote>"
        f"{number_line}\n\n"
        f"⏳  <b>{sc('Attempt')} #{attempt}</b>  —  {phase}\n"
        f"<code>{sc('Attempts')}: {attempt} / 20</code>"
    )


def build_stopped_msg(attempt: int, reason: str = "user") -> str:
    if reason == "user":
        return (
            f"⛔  <b>{sc('Loop Stopped')}</b>\n\n"
            f"<blockquote>{sc('Stopped After')} {attempt} {sc('Attempt(s)')}.</blockquote>"
        )
    elif reason == "max":
        return (
            f"🔚  <b>{sc('Max Attempts Reached')}</b>\n\n"
            f"<blockquote>{sc('Reached Limit Of')} {attempt} {sc('Attempts Without A Match')}.\n"
            f"{sc('Try Again From The Main Menu')}</blockquote>"
        )
    elif reason == "no_balance":
        return (
            f"💸  <b>{sc('Insufficient Balance')}</b>\n\n"
            f"<blockquote>{sc('Your NexNum Balance Is Too Low To Continue.')} "
            f"{sc('Top Up At nexnum.in')}</blockquote>"
        )
    return f"⚠️  {sc('Loop Ended')}: {reason}"


def build_refunded_card(
    number:   str | int,
    order_id: str,
    attempt:  int,
    cost:     int | float = 0,
    platform: "PlatformDef | None" = None,
) -> str:
    """Cancelled / refunded card — matches result card blockquote style."""
    cc, nat  = _split_phone(number)
    cost_tag = f" 💎 {format_balance(cost)}" if cost else ""
    label    = sc(_plat_label(platform))
    flag     = _plat_flag(platform)
    icon     = _plat_icon(platform)
    return (
        f"<blockquote><b>{icon} {label} [{cost_tag}</b> {flag} <b>]</b></blockquote>\n\n"
        f"📱 <b>{sc('Number')} »</b> <code>{cc}</code> <code>{nat}</code>\n\n"
        f"❌  <b>{sc('Order Is Cancelled')}</b>  <code>[{sc('Refunded')}]</code>"
    )


def build_auto_cancel_card(
    number:   str | int,
    order_id: str,
    attempt:  int,
    cost:     int | float = 0,
    platform: "PlatformDef | None" = None,
) -> str:
    """Auto-cancelled card — no SMS received after 10m timeout."""
    cc, nat  = _split_phone(number)
    cost_tag = f" 💎 {format_balance(cost)}" if cost else ""
    label    = sc(_plat_label(platform))
    flag     = _plat_flag(platform)
    icon     = _plat_icon(platform)
    return (
        f"<blockquote><b>{icon} {label} [{cost_tag}</b> {flag} <b>]</b></blockquote>\n\n"
        f"📱 <b>{sc('Number')} »</b> <code>{cc}</code> <code>{nat}</code>\n\n"
        f"⏱️  <b>{sc('Order Is Cancelled')}</b>  <code>[{sc('Refunded')}]</code>"
    )


def build_welcome_msg(has_key: bool, balance: float | None = None) -> str:
    bal_line = ""
    if has_key and balance is not None:
        bal_line = f"\n💎  <b>{sc('Balance')}:</b>  <code>{format_balance(balance)}</code>"
    key_line = (
        f"\n🔑  <b>{sc('Api Key')}:</b>  {sc('Connected')} ✅"
        if has_key
        else f"\n🔑  <b>{sc('Api Key')}:</b>  <code>{sc('Not Set')}</code>"
    )
    return (
        f"🤖  <b>Nᴇxᴄʜᴇᴄᴋᴇʀ</b>\n"
        f"{blockquote(sc('Multi-Platform Registration Checker Via Real NexNum Virtual SIMs'))}"
        f"\n{bal_line}"
        f"{key_line}"
    )


def build_stats_msg(stats: dict, balance: float | None = None) -> str:
    total     = stats.get("total_checks", 0)
    reg       = stats.get("registered_found", 0)
    not_reg   = stats.get("not_registered_found", 0)
    cancelled = stats.get("cancelled", 0)
    bal_line  = (
        f"\n\n💎  <b>{sc('Balance')}:</b>  <code>{format_balance(balance)}</code>"
        if balance is not None else ""
    )
    return (
        f"📊  <b>{sc('Your Stats')}</b>\n\n"
        f"<blockquote>"
        f"├  {sc('Total Checks')}:       <code>{total}</code>\n"
        f"├  ✅ {sc('Registered')}:       <code>{reg}</code>\n"
        f"├  🛑 {sc('Not Registered')}:   <code>{not_reg}</code>\n"
        f"└  🔄 {sc('Cancelled')}:        <code>{cancelled}</code>"
        f"</blockquote>"
        f"{bal_line}"
    )
