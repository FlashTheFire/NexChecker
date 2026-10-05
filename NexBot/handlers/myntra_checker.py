"""NexBot — Core Myntra Checker Handler.

Architecture:
─────────────────────────────────────────────────────────────────────────────
• ONE Telegram message per session (created by /myntra or "� Myntra Checker" button)
• ALL state changes edit that ONE message — no new messages after initial send
• Loop is an asyncio.Task (cancellable via Stop button or Buy Next)
• Myntra checks use the real Playwright Chrome profile (same as myntra_check.py)
  — page.evaluate() fetch with credentials:'include' bypasses Cloudflare CHALLENGE
  — auto-heal: reload /forgot on CHALLENGE, retry up to 3 times
• Cancellations are DEFERRED: orders < CANCEL_MIN_AGE seconds old are queued
  and processed by _bg_cancel_worker every CANCEL_POLL_SECS seconds in parallel
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
)

from core.nexnum_api import nexnum_client, NexNumStatus
from core.myntra_api import myntra_checker
from core import user_store
from utils.config import (
    SERVICE_CODE, COUNTRY_CODE,
    MAX_ATTEMPTS, BULK_DELAY, MIN_BALANCE,
    NO_NUMBERS_RETRY, NO_NUMBERS_DELAY,
    CANCEL_MIN_AGE, CANCEL_POLL_SECS,
)
from utils.formatting import (
    sc, build_result_card, build_progress_msg,
    build_stopped_msg, build_refunded_card,
    format_phone, extract_10, format_balance,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Module-level session state (exported — used by callbacks.py and bot.py)
# ═════════════════════════════════════════════════════════════════════════════

# user_id → True while loop should keep running
_active_sessions: Dict[int, bool] = {}

# user_id → running asyncio.Task
_session_tasks: Dict[int, asyncio.Task] = {}


# ═════════════════════════════════════════════════════════════════════════════
# Deferred Cancel Queue  (background task — runs every CANCEL_POLL_SECS)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class _PendingCancel:
    """An order waiting for the CANCEL_MIN_AGE cooldown before NexNum allows cancel."""
    api_key:   str
    order_id:  str
    queued_at: float = field(default_factory=time.monotonic)
    retries:   int   = 0
    max_retry: int   = 4   # give up after 4 worker cycles (~2 minutes)

_cancel_queue: List[_PendingCancel] = []
_cancel_worker_task: Optional[asyncio.Task] = None


async def _bg_cancel_worker() -> None:
    """Background task: every CANCEL_POLL_SECS, fire all ready cancellations in parallel.

    'Ready' = queued_at is at least CANCEL_MIN_AGE seconds ago.
    Failed cancels are re-queued up to max_retry times, then dropped.
    """
    logger.info("[CancelWorker] background task started — polling every %ds", CANCEL_POLL_SECS)
    while True:
        await asyncio.sleep(CANCEL_POLL_SECS)

        if not _cancel_queue:
            continue

        now   = time.monotonic()
        ready = [
            p for p in _cancel_queue
            if (now - p.queued_at) >= CANCEL_MIN_AGE
        ]
        if not ready:
            logger.debug("[CancelWorker] %d order(s) still cooling down", len(_cancel_queue))
            continue

        logger.info("[CancelWorker] firing %d parallel cancel(s)", len(ready))

        # ── Fire all cancels in parallel ──────────────────────────────────────
        results = await asyncio.gather(
            *(nexnum_client.set_status(p.api_key, p.order_id, 8) for p in ready),
            return_exceptions=True,
        )

        for p, res in zip(ready, results):
            if isinstance(res, Exception):
                # Network/timeout — retry
                p.retries += 1
                if p.retries >= p.max_retry:
                    logger.warning(
                        "[CancelWorker] giving up on order %s after %d retries (exception)",
                        p.order_id, p.retries,
                    )
                    _cancel_queue.remove(p)
                else:
                    p.queued_at = time.monotonic()
                    logger.debug("[CancelWorker] re-queued order %s (retry %d)", p.order_id, p.retries)
                continue

            code   = res.get("code", "")   if isinstance(res, dict) else ""
            status = res.get("status", "") if isinstance(res, dict) else ""

            if res.get("ok"):
                logger.info("[CancelWorker] cancel %s → success", p.order_id)
                _cancel_queue.remove(p)

            elif code in NexNumStatus.CANCEL_TERMINAL:
                # Terminal — OTP received / already cancelled / completed. Drop it.
                logger.warning(
                    "[CancelWorker] terminal '%s' for %s — order finalised (OTP received / cancelled / completed), dropping",
                    code, p.order_id,
                )
                _cancel_queue.remove(p)

            elif res.get("early_denied"):
                # Still within cooldown — just extend and wait
                p.queued_at = time.monotonic()
                logger.debug("[CancelWorker] EARLY_CANCEL_DENIED %s — cooling", p.order_id)

            else:
                # Unknown failure — count as retry
                p.retries += 1
                if p.retries >= p.max_retry:
                    logger.warning(
                        "[CancelWorker] giving up on %s after %d retries (status=%s code=%s)",
                        p.order_id, p.retries, status, code,
                    )
                    _cancel_queue.remove(p)
                else:
                    p.queued_at = time.monotonic()
                    logger.debug("[CancelWorker] re-queued %s (retry %d, code=%s)", p.order_id, p.retries, code)


def schedule_deferred_cancel(api_key: str, order_id: str) -> None:
    """Queue an order for background cancellation after CANCEL_MIN_AGE seconds.

    Safe to call from anywhere — no awaiting needed.
    Duplicate order_ids are silently ignored.
    """
    if any(p.order_id == order_id for p in _cancel_queue):
        return
    _cancel_queue.append(_PendingCancel(api_key=api_key, order_id=order_id))
    logger.debug("[DeferredCancel] queued %s (queue size: %d)", order_id, len(_cancel_queue))


async def try_immediate_cancel(api_key: str, order_id: str) -> bool:
    """Try to cancel right now. Handles all NexNum cancel responses.

    ok           → done
    EARLY_CANCEL → too soon → defer to background queue
    BAD_STATUS   → OTP received, NexNum won't cancel → do NOT retry
    other        → defer with retry limit
    """
    try:
        res = await nexnum_client.set_status(api_key, order_id, 8)
    except Exception as exc:
        logger.warning("[Cancel] exception for %s: %s — deferring", order_id, exc)
        schedule_deferred_cancel(api_key, order_id)
        return False

    if res.get("ok"):
        logger.info("[Cancel] immediate cancel success: %s", order_id)
        return True

    code = res.get("code", "")

    if code in NexNumStatus.CANCEL_TERMINAL:
        logger.info(
            "[Cancel] terminal '%s' for %s — check getStatus for OTP before deciding",
            code, order_id,
        )
        return code   # ← return the code string (e.g. "BAD_STATUS") so caller can getStatus

    if res.get("early_denied"):
        logger.info("[Cancel] EARLY_CANCEL_DENIED for %s — deferring", order_id)
    else:
        logger.info("[Cancel] cancel failed (%s) for %s — deferring", code or res.get("status"), order_id)

    schedule_deferred_cancel(api_key, order_id)
    return False


# ═════════════════════════════════════════════════════════════════════════════
# Inline keyboard builders
# ═════════════════════════════════════════════════════════════════════════════

def _filter_markup() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton(f"✅  {sc('Registered')}",     callback_data="myntra_filter:REGISTERED"),
        InlineKeyboardButton(f"🛑  {sc('Not Registered')}", callback_data="myntra_filter:NOT_REGISTERED"),
    )
    kb.add(InlineKeyboardButton(f"📊  {sc('Any')}", callback_data="myntra_filter:ANY"))
    return kb


def _progress_markup(order_id: str = "") -> InlineKeyboardMarkup:
    """Running loop — Stop and Skip (buy next, discard current) on same row."""
    kb = InlineKeyboardMarkup(row_width=2)
    if order_id:
        kb.row(
            InlineKeyboardButton(f"⛔  {sc('Stop Loop')}",  callback_data="myntra_stop"),
            InlineKeyboardButton(f"🛒  {sc('Skip')}",      callback_data=f"myntra_next:{order_id}"),
        )
    else:
        kb.add(InlineKeyboardButton(f"⛔  {sc('Stop Loop')}", callback_data="myntra_stop"))
    return kb


def _result_markup(order_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"🛒  {sc('Buy Next')}",     callback_data=f"myntra_next:{order_id}"),
        InlineKeyboardButton(f"🔄  {sc('Refresh Sms')}",  callback_data=f"myntra_refresh:{order_id}"),
    )
    kb.add(InlineKeyboardButton(
        f"❌  {sc('Cancel Purchase')}", callback_data=f"myntra_cancel:{order_id}"))
    return kb


def _refunded_markup(order_id: str = "") -> InlineKeyboardMarkup:
    """Cancelled/refunded — Check Another + optional Buy Next on same row."""
    kb = InlineKeyboardMarkup(row_width=2)
    if order_id:
        kb.row(
            InlineKeyboardButton(f"🛒  {sc('Buy Next')}",       callback_data=f"myntra_next:{order_id}"),
            InlineKeyboardButton(f"🔄  {sc('Check Another')}", callback_data="myntra_menu"),
        )
    else:
        kb.add(InlineKeyboardButton(f"🔄  {sc('Check Another')}", callback_data="myntra_menu"))
    return kb


def _stopped_markup() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🔄  {sc('Try Again')}", callback_data="myntra_menu"))
    return kb


def _home_markup() -> InlineKeyboardMarkup:
    """Back-to-filter button shown on error / info screens."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🏠  {sc('Back To Filter')}", callback_data="myntra_menu"))
    return kb


# ═════════════════════════════════════════════════════════════════════════════
# Shared safe-edit helper
# ═════════════════════════════════════════════════════════════════════════════

async def safe_edit(
    bot:    AsyncTeleBot,
    cid:    int,
    mid:    int,
    text:   str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    """Edit a Telegram message.  Silently ignores 'message is not modified'."""
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=cid,
            message_id=mid,
            reply_markup=markup,
            parse_mode="HTML",
        )
        return True
    except Exception as exc:
        if "message is not modified" in str(exc).lower():
            return False
        logger.warning("safe_edit failed (cid=%s mid=%s): %s", cid, mid, exc)
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Main handler class
# ═════════════════════════════════════════════════════════════════════════════

class MyntraCheckerHandler:

    def __init__(self, bot: AsyncTeleBot) -> None:
        self.bot = bot

    # ── Startup ───────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Launch the background cancel worker.  Call once inside main() after
        the event loop is running."""
        global _cancel_worker_task
        if _cancel_worker_task is None or _cancel_worker_task.done():
            _cancel_worker_task = asyncio.create_task(_bg_cancel_worker())

    # ─────────────────────────────────────────────────────────────────────────
    # Entry points
    # ─────────────────────────────────────────────────────────────────────────

    async def handle_myntra_command(self, message: Message) -> None:
        """/myntra command — send ONE checker message with filter selection."""
        user_id = message.from_user.id
        chat_id = message.chat.id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            from handlers.start import _home_markup
            sent = await self.bot.send_message(
                chat_id,
                f"🔑  <b>{sc('No Api Key Set')}</b>\n\n"
                f"<blockquote>{sc('Tap')} <b>🔑 {sc('Set Api Key')}</b> {sc('From The Main Menu To Get Started.')}</blockquote>",
                parse_mode="HTML",
                reply_markup=_home_markup(False),
            )
            return

        # Stop & clean up any previous session
        await self._stop_session(user_id, cancel_pending=False)

        # Send the ONE session message
        sent = await self.bot.send_message(
            chat_id,
            self._filter_text(),
            reply_markup=_filter_markup(),
            parse_mode="HTML",
        )

        # Persist session message coordinates
        await user_store.update_order(user_id, {
            "message_id": sent.message_id,
            "chat_id":    chat_id,
            "status":     "IDLE",
        })

    # ── Filter selection (from callback) ─────────────────────────────────────

    async def handle_filter_selection(
        self, call: CallbackQuery, filter_mode: str
    ) -> None:
        """User tapped a filter button — edit message and launch checker loop."""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(
                call.id, "⚠️ No Api Key — Tap 🔑 Set Api Key From The Main Menu", show_alert=True
            )
            return

        # If a loop is already running for this user, stop it first
        await self._stop_session(user_id, cancel_pending=False)

        # Save filter preference + session coordinates
        await user_store.set_preference(user_id, "filter", filter_mode)
        await user_store.update_order(user_id, {
            "message_id": msg_id,
            "chat_id":    chat_id,
            "status":     "RUNNING",
        })

        filter_labels = {
            "REGISTERED":     f"✅ {sc('Registered')}",
            "NOT_REGISTERED": f"🛑 {sc('Not Registered')}",
            "ANY":            f"📊 {sc('Any')}",
        }
        await self.bot.answer_callback_query(
            call.id,
            f"🚀 {sc('Starting')} — {filter_labels.get(filter_mode, filter_mode)}"
        )

        # Edit to initial progress state
        await safe_edit(
            self.bot, chat_id, msg_id,
            build_progress_msg(1, f"💳  {sc('Initialising…')}", filter_mode),
            _progress_markup(),
        )

        # Launch loop as background Task
        _active_sessions[user_id] = True
        task = asyncio.create_task(
            self._run_checker_loop(user_id, chat_id, msg_id, filter_mode, api_key),
            name=f"checker_{user_id}",
        )
        _session_tasks[user_id] = task
        task.add_done_callback(
            lambda t: asyncio.create_task(
                self._on_task_done(t, user_id, chat_id, msg_id)
            )
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Core checker loop  ← THE HEART OF THE BOT
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_checker_loop(
        self,
        user_id:     int,
        chat_id:     int,
        msg_id:      int,
        filter_mode: str,
        api_key:     str,
    ) -> None:
        """Sequential purchase → parallel-heal Myntra check → deferred cancel.

        Flow per iteration:
          1. Edit message → "Buying number…"
          2. Call NexNum getNumber (service=nl, country=22)
          3. Edit message → "Checking +91 XXXXX…"
          4. Call Myntra /forgot with parallel heal (3 simultaneous requests)
          5a. MATCH  → fetch balance, show result card + action buttons → STOP
          5b. NO MATCH → schedule deferred cancel, brief delay, next iteration
        """
        attempt          = 0
        no_numbers_streak = 0

        # ── Guard: Chrome context must be ready ───────────────────────────────
        if not myntra_checker.is_ready:
            await safe_edit(
                self.bot, chat_id, msg_id,
                f"⚠️  <b>{sc('Chrome Not Ready')}</b>\n\n"
                f"<blockquote>"
                f"{sc('The Myntra Browser Session Is Not Started.')}\n"
                f"{sc('Run')} <code>python warmup.py</code> {sc('Then Restart The Bot.')}"
                f"</blockquote>",
                _home_markup(),
            )
            return

        try:
            while _active_sessions.get(user_id, False) and attempt < MAX_ATTEMPTS:
                attempt += 1

                # ── Guard: balance check every 5 attempts ─────────────────────
                if attempt % 5 == 1:
                    bal = await nexnum_client.get_balance(api_key)
                    if bal["ok"] and bal["balance"] < MIN_BALANCE:
                        await safe_edit(
                            self.bot, chat_id, msg_id,
                            build_stopped_msg(attempt, "no_balance"),
                            _stopped_markup(),
                        )
                        return

                # ─────────────────────────────────────────────────────────────
                # STEP 1: Buy a number
                # ─────────────────────────────────────────────────────────────
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_progress_msg(attempt, f"💳  {sc('Buying Number…')}", filter_mode),
                    _progress_markup(),
                )

                buy = await nexnum_client.get_number(api_key, SERVICE_CODE, COUNTRY_CODE)

                # ── Handle purchase errors ────────────────────────────────────
                if not buy["ok"]:
                    err_status = buy.get("status")

                    if err_status == NexNumStatus.NO_BALANCE:
                        await safe_edit(
                            self.bot, chat_id, msg_id,
                            build_stopped_msg(attempt, "no_balance"),
                            _stopped_markup(),
                        )
                        return

                    if err_status == NexNumStatus.BAD_KEY:
                        await safe_edit(
                            self.bot, chat_id, msg_id,
                            f"🔑  <b>{sc('Invalid Api Key')}</b>\n\n"
                            f"<blockquote>{sc('NexNum Rejected Your Key.')}\n"
                            f"{sc('Tap')} <b>🔑 {sc('Set Api Key')}</b> {sc('To Update It.')}</blockquote>",
                            _home_markup(),
                        )
                        return

                    if err_status == NexNumStatus.BANNED:
                        await safe_edit(
                            self.bot, chat_id, msg_id,
                            f"🚫  <b>{sc('Account Banned')}</b>\n\n"
                            f"<blockquote>{sc('Your NexNum Account Is Banned.')}</blockquote>",
                            _home_markup(),
                        )
                        return

                    if err_status == NexNumStatus.NO_NUMBERS:
                        no_numbers_streak += 1
                        if no_numbers_streak >= NO_NUMBERS_RETRY:
                            await safe_edit(
                                self.bot, chat_id, msg_id,
                                f"📭  <b>{sc('No Numbers Available')}</b>\n\n"
                                f"<blockquote>"
                                f"{sc('NexNum Has No')} <code>nl</code> {sc('Numbers Right Now.')}\n"
                                f"{sc('Try Again Later With /myntra.')}"
                                f"</blockquote>",
                                _stopped_markup(),
                            )
                            return

                        await safe_edit(
                            self.bot, chat_id, msg_id,
                            build_progress_msg(
                                attempt,
                                f"📭  {sc('No Numbers')} — "
                                f"{sc('Retrying In')} {int(NO_NUMBERS_DELAY)}s "
                                f"<code>({no_numbers_streak}/{NO_NUMBERS_RETRY})</code>",
                                filter_mode,
                            ),
                            _progress_markup(),
                        )
                        await asyncio.sleep(NO_NUMBERS_DELAY)
                        attempt -= 1  # don't penalise the attempt counter
                        continue

                    # Generic / unknown error — retry once
                    await safe_edit(
                        self.bot, chat_id, msg_id,
                        build_progress_msg(
                            attempt,
                            f"⚠️  {sc('Error')}: <code>{buy.get('error', 'unknown')}</code> — "
                            f"{sc('Retrying…')}",
                            filter_mode,
                        ),
                        _progress_markup(),
                    )
                    await asyncio.sleep(2.0)
                    attempt -= 1
                    continue

                # ─────────────────────────────────────────────────────────────
                # Purchase succeeded
                # ─────────────────────────────────────────────────────────────
                no_numbers_streak = 0
                order_id = buy["order_id"]
                number   = buy["number"]
                mobile   = extract_10(number)   # 10-digit, no country prefix

                # Persist current order immediately — also clear any stale OTP
                # from a previous order so the new poller starts with a blank slate.
                await user_store.update_order(user_id, {
                    "order_id":      order_id,
                    "number":        number,
                    "service":       SERVICE_CODE,
                    "country":       COUNTRY_CODE,
                    "cost":          buy.get("cost", 0),
                    "status":        "CHECKING",
                    "myn_result":    "",           # cleared — filled after Myntra check
                    "last_otp":      "",           # ← clears stale OTP from prev order
                    "last_full_sms": "",           # ← clears stale SMS from prev order
                    "message_id":    msg_id,
                    "chat_id":       chat_id,
                    "attempt":       attempt,
                    "purchased_at":  datetime.now().isoformat(),
                })

                # ─────────────────────────────────────────────────────────────
                # STEP 2: Check Myntra — parallel heal retries (fast!)
                # ─────────────────────────────────────────────────────────────
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_progress_msg(
                        attempt,
                        f"🔍  {sc('Checking')}",
                        filter_mode,
                        number=number,
                    ),
                    _progress_markup(order_id),
                )

                # myntra_checker.check_number fires 3 parallel requests
                # and returns on first conclusive answer (or UNKNOWN if all fail)
                myntra_result = await myntra_checker.check_number(mobile)
                status        = myntra_result.get("status", "UNKNOWN")

                # ─────────────────────────────────────────────────────────────
                # STEP 3: Match check
                # ─────────────────────────────────────────────────────────────
                is_conclusive = status in ("REGISTERED", "NOT_REGISTERED")
                is_match = (
                    is_conclusive and (
                        filter_mode == "ANY"
                        or filter_mode == status
                    )
                )

                if is_match:
                    # ── MATCH FOUND ───────────────────────────────────────────
                    cost = buy.get("cost", 0)

                    # Store both lifecycle status AND Myntra result separately.
                    # myn_result (REGISTERED/NOT_REGISTERED) is never overwritten
                    # by _persist_otp so Refresh SMS always reads the correct value.
                    await user_store.update_order(user_id, {
                        "status":     status,
                        "myn_result": status,   # ← persists across OTP/COMPLETED state
                    })
                    await user_store.increment_stat(user_id, status)

                    await safe_edit(
                        self.bot, chat_id, msg_id,
                        build_result_card(number, status, order_id, attempt, cost),
                        _result_markup(order_id),
                    )

                    # ── Auto-poll for OTP in background ───────────────────────
                    from core.sms_poller import start_sms_poller
                    start_sms_poller(
                        bot=self.bot,   user_id=user_id,
                        chat_id=chat_id, msg_id=msg_id,
                        api_key=api_key, order_id=order_id,
                        number=number,   myn_status=status,
                        cost=cost,       attempt=attempt,
                    )
                    return  # ← loop ends; action buttons + poller take over

                # ─────────────────────────────────────────────────────────────
                # STEP 4: No match — defer cancel, continue
                # ─────────────────────────────────────────────────────────────
                await user_store.increment_stat(user_id, "cancelled")
                schedule_deferred_cancel(api_key, order_id)

                await asyncio.sleep(BULK_DELAY)

            # ── Max attempts exhausted ─────────────────────────────────────────
            if _active_sessions.get(user_id, False):
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_stopped_msg(attempt, "max"),
                    _stopped_markup(),
                )

        except asyncio.CancelledError:
            logger.info("[Loop] user %d loop cancelled", user_id)
            raise   # let _on_task_done handle the UI update

        finally:
            _active_sessions.pop(user_id, None)
            _session_tasks.pop(user_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Task completion callback
    # ─────────────────────────────────────────────────────────────────────────

    async def _on_task_done(
        self,
        task:    asyncio.Task,
        user_id: int,
        chat_id: int,
        msg_id:  int,
    ) -> None:
        """Fires when the checker Task finishes — handles cancellation and crashes."""
        if task.cancelled():
            order = await user_store.get_last_order(user_id)
            # Only overwrite if we haven't already shown a result / refunded card
            if order.get("status") not in ("REGISTERED", "NOT_REGISTERED", "REFUNDED"):
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_stopped_msg(0, "user"),
                    _stopped_markup(),
                )
        elif task.exception():
            exc = task.exception()
            logger.exception("[Loop] unhandled exception for user %d", user_id, exc_info=exc)
            await safe_edit(
                self.bot, chat_id, msg_id,
                f"⚠️  <b>{sc('Internal Error')}</b>\n\n"
                f"<blockquote><code>{str(exc)[:300]}</code></blockquote>",
                _stopped_markup(),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Public helpers (called by callbacks.py)
    # ─────────────────────────────────────────────────────────────────────────

    async def _stop_session(
        self,
        user_id:        int,
        cancel_pending: bool = True,
    ) -> None:
        """Cancel any running loop for this user.

        If cancel_pending=True and the last order was in CHECKING state,
        schedule it for deferred background cancellation.
        """
        _active_sessions[user_id] = False

        task = _session_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if cancel_pending:
            api_key = await user_store.get_api_key(user_id)
            order   = await user_store.get_last_order(user_id)
            oid     = order.get("order_id")
            if api_key and oid and order.get("status") == "CHECKING":
                schedule_deferred_cancel(api_key, oid)

    async def show_filter_menu(
        self, chat_id: int, msg_id: int, user_id: int
    ) -> None:
        """Edit session message back to the filter selection screen."""
        await safe_edit(
            self.bot, chat_id, msg_id,
            self._filter_text(),
            _filter_markup(),
        )

    async def restart_loop(
        self,
        user_id:     int,
        chat_id:     int,
        msg_id:      int,
        filter_mode: str,
        api_key:     str,
    ) -> None:
        """Stop any current loop and immediately start a new one (used by Buy Next)."""
        await self._stop_session(user_id, cancel_pending=False)

        await safe_edit(
            self.bot, chat_id, msg_id,
            build_progress_msg(1, f"💳  {sc('Buying Next Number…')}", filter_mode),
            _progress_markup(),
        )

        _active_sessions[user_id] = True
        task = asyncio.create_task(
            self._run_checker_loop(user_id, chat_id, msg_id, filter_mode, api_key),
            name=f"checker_{user_id}",
        )
        _session_tasks[user_id] = task
        task.add_done_callback(
            lambda t: asyncio.create_task(
                self._on_task_done(t, user_id, chat_id, msg_id)
            )
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Static text
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _filter_text() -> str:
        return (
            f"<b>📦 {sc('Myntra Checker')}</b>\n\n"
            f"<blockquote>"
            f"{sc('Choose A Status Filter.')}\n"
            f"{sc('The Bot Will Buy Real NexNum')} <code>nl</code> "
            f"{sc('Numbers (India) And Hit The Myntra Forgot-Password Api')}\n"
            f"{sc('Until The Result Matches Your Filter.')}"
            f"</blockquote>"
        )
