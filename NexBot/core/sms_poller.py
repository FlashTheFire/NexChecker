"""core/sms_poller.py — Auto OTP polling for NexBot.

Features:
  • Polls NexNum getStatus every 5s after result card shown
  • Persists OTP + marks order COMPLETED in user_store on first receipt
  • Edits result card with OTP + removes Cancel button
  • Sends NEW reply per unique OTP with full SMS text + sender
  • Each SMS notification has [📋 Copy Code] [📄 Copy Full SMS] buttons
  • Deduplication — never shows same OTP twice
  • Polls up to 19 minutes (order expiry)
  • Restored on bot restart:
      REGISTERED/CHECKING → resume polling
      COMPLETED           → re-edit card with saved OTP immediately (no polling)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton

from core.nexnum_api import nexnum_client
from utils.formatting import sc, build_result_card, extract_10

logger = logging.getLogger(__name__)

POLL_INTERVAL     = 5
MAX_POLL_DURATION = 19 * 60

_sms_pollers: dict[int, asyncio.Task] = {}

# {order_id: {"code": str, "full_sms": str}}  — for copy button callbacks
_sms_store: dict[str, dict] = {}


# ── Markup helpers ────────────────────────────────────────────────────────────

def _result_markup_no_cancel(order_id: str) -> InlineKeyboardMarkup:
    """Result card buttons WITHOUT Cancel (shown after first OTP received)."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton(f"🛒  {sc('Buy Next')}",    callback_data=f"myntra_next:{order_id}"),
        InlineKeyboardButton(f"🔄  {sc('Refresh Sms')}", callback_data=f"myntra_refresh:{order_id}"),
    )
    return kb


def _sms_msg_markup(order_id: str, code: str, full_sms: str = "") -> InlineKeyboardMarkup:
    """Both buttons use native CopyTextButton — no callback fires, instant clipboard copy."""
    kb = InlineKeyboardMarkup(row_width=2)
    # Truncate full_sms to Telegram's 256-char CopyTextButton limit
    sms_copy_text = (full_sms[:253] + "…") if len(full_sms) > 256 else (full_sms or code)
    kb.row(
        InlineKeyboardButton(
            f"{sc('Copy Code')}",
            copy_text=CopyTextButton(text=code),
        ),
        InlineKeyboardButton(
            f"{sc('Copy Full Sms')}",
            copy_text=CopyTextButton(text=sms_copy_text),
        ),
    )
    return kb


# ── SMS notification text ─────────────────────────────────────────────────────

def _sms_notification_text(
    number:    str,
    code:      str,
    full_sms:  str,
    sender:    str,
    all_codes: list[str],
) -> str:
    digits = extract_10(number)

    header = (
        f"<blockquote><b>🗨️ {sc('New Message Received')} "
        f"[ <code>+91</code> <code>{digits}</code> ]</b></blockquote>\n"
    )
    sender_line = f"\n📨 <b>{sc('Sender')} »</b>  <code>{sender}</code>" if sender else ""
    otp_line    = f"\n🔐 <b>{sc('Otp Code')} »</b>  <code>{code}</code>"

    sms_body = ""
    if full_sms and full_sms != code:
        sms_body = f"\n\n<blockquote>{full_sms}</blockquote>"

    history = ""
    if len(all_codes) > 1:
        history = f"\n\n<b>{sc('All Codes')}:</b>  " + "  ".join(f"<code>{c}</code>" for c in all_codes)

    return f"{header}{sender_line}{otp_line}{sms_body}{history}"


# ── Persist OTP to store ──────────────────────────────────────────────────────

async def _persist_otp(user_id: int, code: str, full_sms: str) -> None:
    """Mark order as COMPLETED and save OTP in user_store."""
    try:
        from core import user_store
        await user_store.update_order(user_id, {
            "status":         "COMPLETED",
            "last_otp":       code,
            "last_full_sms":  full_sms,
            "otp_received_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("[SmsPoller] persist_otp failed: %s", exc)


# ── Poller coroutine ──────────────────────────────────────────────────────────

async def _run_poller(
    bot:        AsyncTeleBot,
    user_id:    int,
    chat_id:    int,
    msg_id:     int,
    api_key:    str,
    order_id:   str,
    number:     str,
    myn_status: str,
    cost:       int | float,
    attempt:    int,
) -> None:
    seen_codes:     list[str] = []
    cancel_removed: bool      = False
    elapsed:        int       = 0

    # Pre-seed seen_codes with already-sent OTPs (from a prior poller run on this order)
    # so a restarted poller never re-delivers the same code.
    try:
        from core import user_store as _us
        _prev = await _us.get_last_order(user_id)
        if _prev.get("order_id") == order_id and _prev.get("last_otp"):
            seen_codes.append(_prev["last_otp"])
            logger.info("[SmsPoller] pre-seeded seen=%s for order=%s", seen_codes, order_id)
    except Exception:
        pass

    logger.info("[SmsPoller] started order=%s user=%s", order_id, user_id)

    while elapsed < MAX_POLL_DURATION:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        try:
            status_res = await nexnum_client.get_status(api_key, order_id)
            raw        = status_res.get("status",   "")
            code       = status_res.get("code",     "").strip()
            full_sms   = status_res.get("full_sms", "").strip()
            sender     = status_res.get("sender",   "").strip()

            if raw in ("ACCESS_CANCEL", "STATUS_CANCEL", "ACCESS_ACTIVATION"):
                logger.info("[SmsPoller] terminal %s order=%s", raw, order_id)
                break

            if raw == "STATUS_OK" and code and code not in seen_codes:
                seen_codes.append(code)
                logger.info("[SmsPoller] order=%s new OTP=%s", order_id, code)

                # ── Persist to store (COMPLETED + last_otp) ───────────────────
                _sms_store[order_id] = {"code": code, "full_sms": full_sms}
                await _persist_otp(user_id, code, full_sms)

                # ── 1. Edit result card: add OTP + remove Cancel ──────────────
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=build_result_card(number, myn_status, order_id, attempt, cost, code),
                        parse_mode="HTML",
                        reply_markup=_result_markup_no_cancel(order_id),
                    )
                    cancel_removed = True
                except Exception as e:
                    logger.warning("[SmsPoller] edit result card failed: %s", e)
                    if not cancel_removed:
                        cancel_removed = True
                        try:
                            await bot.edit_message_reply_markup(
                                chat_id=chat_id, message_id=msg_id,
                                reply_markup=_result_markup_no_cancel(order_id),
                            )
                        except Exception:
                            pass

                # ── 2. Send new reply with full SMS + copy buttons ─────────────
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=_sms_notification_text(number, code, full_sms, sender, seen_codes),
                        parse_mode="HTML",
                        reply_to_message_id=msg_id,
                        reply_markup=_sms_msg_markup(order_id, code, full_sms),
                    )
                except Exception as send_err:
                    logger.warning("[SmsPoller] send_message failed: %s", send_err)

                # Poller keeps running to catch additional SMS (e.g. marketing, re-send OTPs)

        except asyncio.CancelledError:
            logger.info("[SmsPoller] cancelled order=%s", order_id)
            break
        except Exception as exc:
            logger.warning("[SmsPoller] poll error order=%s: %s", order_id, exc)

    logger.info("[SmsPoller] done order=%s codes=%d", order_id, len(seen_codes))
    _sms_pollers.pop(user_id, None)


# ── Public API ────────────────────────────────────────────────────────────────

def start_sms_poller(
    bot:        AsyncTeleBot,
    user_id:    int,
    chat_id:    int,
    msg_id:     int,
    api_key:    str,
    order_id:   str,
    number:     str,
    myn_status: str         = "REGISTERED",
    cost:       int | float = 0,
    attempt:    int         = 1,
) -> None:
    """Start (or restart) the SMS poller for a user. Fire-and-forget."""
    stop_sms_poller(user_id)
    task = asyncio.get_event_loop().create_task(
        _run_poller(bot, user_id, chat_id, msg_id, api_key, order_id, number, myn_status, cost, attempt)
    )
    _sms_pollers[user_id] = task
    logger.info("[SmsPoller] task created user=%s order=%s", user_id, order_id)


def stop_sms_poller(user_id: int) -> None:
    """Cancel any running poller for this user."""
    task = _sms_pollers.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        logger.info("[SmsPoller] cancelled user=%s", user_id)


async def restore_pollers(bot: AsyncTeleBot) -> int:
    """Called on bot startup — restore pollers and repair stale cards.

    REGISTERED/CHECKING  → restart poller (order still active, may get OTP)
    COMPLETED            → re-edit card immediately with saved OTP, no polling
    """
    from core.user_store import load_all_active_orders
    entries = await load_all_active_orders(max_age_minutes=19)
    count = 0

    for entry in entries:
        uid      = entry["user_id"]
        status   = entry["status"]
        order_id = entry["order_id"]

        # DB status → real Myntra status for build_result_card
        # 'CHECKING' / 'REGISTERED' / 'COMPLETED' are DB states.
        # The Myntra check result is always REGISTERED when we start a poller
        # (we only poll for OTP on REGISTERED matches).
        myn_status = "REGISTERED"

        if status == "COMPLETED":
            # Re-edit the result card with the saved OTP so it shows correctly
            saved_otp    = entry.get("last_otp") or ""
            saved_sms    = entry.get("last_full_sms") or ""
            if saved_otp:
                # Seed _sms_store so Copy Full SMS works immediately without DB lookup
                _sms_store[order_id] = {"code": saved_otp, "full_sms": saved_sms}
                try:
                    await bot.edit_message_text(
                        chat_id=entry["chat_id"],
                        message_id=entry["message_id"],
                        text=build_result_card(
                            entry["number"], myn_status, order_id,
                            entry["attempt"], entry["cost"], saved_otp,
                        ),
                        parse_mode="HTML",
                        reply_markup=_result_markup_no_cancel(order_id),
                    )
                    logger.info(
                        "[SmsPoller] repaired COMPLETED card user=%s order=%s otp=%s",
                        uid, order_id, saved_otp,
                    )
                except Exception as e:
                    logger.warning("[SmsPoller] repair COMPLETED card failed: %s", e)
            count += 1

        else:
            # REGISTERED / CHECKING — restart active poller
            # The poller pre-seeds seen_codes from last_otp in user_store,
            # so it will never re-deliver an OTP already sent.
            logger.info("[SmsPoller] restoring poller user=%s order=%s", uid, order_id)
            start_sms_poller(
                bot=bot,
                user_id=uid,
                chat_id=entry["chat_id"],
                msg_id=entry["message_id"],
                api_key=entry["api_key"],
                order_id=order_id,
                number=entry["number"],
                myn_status=myn_status,   # always REGISTERED (only REGISTERED orders get polled)
                cost=entry.get("cost", 0),
                attempt=entry.get("attempt", 1),
            )
            count += 1

    if count:
        logger.info("[SmsPoller] startup: handled %d order(s)", count)
    return count
