"""core/sms_poller.py — Auto OTP polling for NexBot.

Features:
  • Polls NexNum getStatus every 5s after result card shown
  • Iterates full sms[] array — deduplicates by SMS id (not by code)
      → Same OTP digits sent twice = two different ids = BOTH forwarded
      → Re-polling same SMS (every 5s) = same id = skipped
  • Timestamps on every notification (IST, from sms.dateTime)
  • Persists seen_sms_ids + OTP in user_store across bot restarts
  • Edits result card with latest OTP + removes Cancel button
  • Each SMS notification has [Copy Code] [Copy Full SMS] native buttons
  • Polls up to 19 minutes (order expiry)
  • Restored on bot restart:
      REGISTERED/CHECKING → resume polling (pre-seeds seen ids)
      COMPLETED           → re-edit card with saved OTP immediately
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

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

IST = timezone(timedelta(hours=5, minutes=30))


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(dt_raw: str) -> str:
    """Convert NexNum dateTime string (UTC) to IST HH:MM AM/PM.
    Input:  "2026-10-05 16:22:42"
    Output: "9:52 PM"  (IST = UTC+5:30)
    """
    if not dt_raw:
        return ""
    try:
        dt_utc = datetime.strptime(dt_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(IST)
        # %I gives 01-12; lstrip("0") removes leading zero cross-platform
        return dt_ist.strftime("%I:%M %p").lstrip("0")   # e.g. "9:52 PM"
    except Exception:
        return ""


# ── SMS notification text ─────────────────────────────────────────────────────

def _sms_notification_text(
    number:    str,
    code:      str,
    full_sms:  str,
    sender:    str,
    all_codes: list[str],
    dt_raw:    str = "",
) -> str:
    digits    = extract_10(number)
    time_str  = _fmt_time(dt_raw)
    time_part = f"  <code>{time_str}</code>" if time_str else ""

    header = (
        f"<blockquote><b>🗨️ {sc('New Message Received')} "
        f"[ <code>+91</code> <code>{digits}</code> ]{time_part}</b></blockquote>\n"
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

async def _persist_otp(
    user_id:  int,
    code:     str,
    full_sms: str,
    seen_ids: list[str] | None = None,
) -> None:
    """Mark order as COMPLETED and save OTP + seen SMS ids in user_store."""
    try:
        from core import user_store
        payload: dict = {
            "status":          "COMPLETED",
            "last_otp":        code,
            "last_full_sms":   full_sms,
            "otp_received_at": datetime.now(timezone.utc).isoformat(),
        }
        if seen_ids is not None:
            payload["seen_sms_ids"] = seen_ids
        await user_store.update_order(user_id, payload)
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
    # Dedup by SMS id, NOT by code.
    # NexNum assigns a unique id per received SMS.
    # Same OTP digits sent twice → two different ids → both forwarded.
    # Re-polling same SMS every 5s → same id → skipped.
    seen_ids:       set[str]  = set()
    seen_codes:     list[str] = []   # for "All Codes" history display only
    cancel_removed: bool      = False
    elapsed:        int       = 0

    # Pre-seed seen_ids from a previous poller run on this exact order
    # so a restarted bot never re-delivers SMS already sent before restart.
    try:
        from core import user_store as _us
        _prev = await _us.get_last_order(user_id)
        if _prev.get("order_id") == order_id:
            raw_ids = _prev.get("seen_sms_ids") or []
            if isinstance(raw_ids, list):
                seen_ids.update(raw_ids)
            last_otp = _prev.get("last_otp", "")
            if last_otp:
                seen_codes.append(last_otp)
            if seen_ids:
                logger.info("[SmsPoller] pre-seeded %d seen ids for order=%s", len(seen_ids), order_id)
    except Exception:
        pass

    logger.info("[SmsPoller] started order=%s user=%s", order_id, user_id)

    while elapsed < MAX_POLL_DURATION:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        try:
            status_res = await nexnum_client.get_status(api_key, order_id)
            raw        = status_res.get("status", "")
            sms_list   = status_res.get("sms", [])   # full array, newest-first from API

            if raw in ("ACCESS_CANCEL", "STATUS_CANCEL", "ACCESS_ACTIVATION"):
                logger.info("[SmsPoller] terminal %s order=%s", raw, order_id)
                break

            if raw != "STATUS_OK" or not sms_list:
                continue

            # Iterate ALL SMS entries; send oldest-new first (chronological order)
            for sms in reversed(sms_list):
                sms_id   = sms.get("id",       "").strip()
                code     = sms.get("code",     "").strip()
                full_sms = sms.get("text",     "").strip()
                sender   = sms.get("sender",   "").strip()
                dt_raw   = sms.get("dateTime", "")   # "2026-10-05 16:22:42" UTC

                if not sms_id or not code:
                    continue
                if sms_id in seen_ids:
                    continue   # already delivered in this or previous session

                # ── New unique SMS ────────────────────────────────────────────
                seen_ids.add(sms_id)
                if code not in seen_codes:
                    seen_codes.append(code)

                logger.info(
                    "[SmsPoller] order=%s new SMS id=%.16s code=%s time=%s",
                    order_id, sms_id, code, dt_raw,
                )

                # Persist COMPLETED + latest OTP + full seen_ids list
                _sms_store[order_id] = {"code": code, "full_sms": full_sms}
                await _persist_otp(user_id, code, full_sms, list(seen_ids))

                # ── 1. Edit result card (only on first OTP — cancel removed once) ─
                if not cancel_removed:
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
                        cancel_removed = True  # don't keep retrying
                        try:
                            await bot.edit_message_reply_markup(
                                chat_id=chat_id, message_id=msg_id,
                                reply_markup=_result_markup_no_cancel(order_id),
                            )
                        except Exception:
                            pass

                # ── 2. Send SMS notification with timestamp ───────────────────
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=_sms_notification_text(
                            number, code, full_sms, sender, seen_codes, dt_raw
                        ),
                        parse_mode="HTML",
                        reply_to_message_id=msg_id,
                        reply_markup=_sms_msg_markup(order_id, code, full_sms),
                    )
                except Exception as send_err:
                    logger.warning("[SmsPoller] send_message failed: %s", send_err)

        except asyncio.CancelledError:
            logger.info("[SmsPoller] cancelled order=%s", order_id)
            break
        except Exception as exc:
            logger.warning("[SmsPoller] poll error order=%s: %s", order_id, exc)

    logger.info("[SmsPoller] done order=%s sms_count=%d", order_id, len(seen_ids))
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

        # myn_result stores the actual Myntra check result (REGISTERED/NOT_REGISTERED).
        # Fall back to REGISTERED since only REGISTERED orders get polled.
        myn_status = entry.get("myn_result") or "REGISTERED"
        if myn_status not in ("REGISTERED", "NOT_REGISTERED"):
            myn_status = "REGISTERED"

        if status == "COMPLETED":
            saved_otp  = entry.get("last_otp") or ""
            saved_sms  = entry.get("last_full_sms") or ""
            if saved_otp:
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
            # Pre-seeding of seen_ids happens inside _run_poller from user_store.
            logger.info("[SmsPoller] restoring poller user=%s order=%s", uid, order_id)
            start_sms_poller(
                bot=bot,
                user_id=uid,
                chat_id=entry["chat_id"],
                msg_id=entry["message_id"],
                api_key=entry["api_key"],
                order_id=order_id,
                number=entry["number"],
                myn_status=myn_status,
                cost=entry.get("cost", 0),
                attempt=entry.get("attempt", 1),
            )
            count += 1

    if count:
        logger.info("[SmsPoller] startup: handled %d order(s)", count)
    return count
