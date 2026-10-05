"""NexBot — Inline callback dispatcher.

Every callback_data starting with "myntra_" is routed here.
All state changes edit the session message in-place — no new messages.
"""
from __future__ import annotations

import asyncio
import logging

from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.nexnum_api import nexnum_client, NexNumStatus
from core import user_store
from utils.formatting import (
    sc, build_refunded_card, build_result_card,
    build_stats_msg, build_welcome_msg, format_balance,
)
from handlers.myntra_checker import (
    MyntraCheckerHandler,
    _active_sessions, _session_tasks,
    schedule_deferred_cancel, try_immediate_cancel,
    _result_markup, _refunded_markup, _stopped_markup,
    _home_markup, safe_edit,
)

logger = logging.getLogger(__name__)


class CallbackHandler:

    def __init__(self, bot: AsyncTeleBot, checker: MyntraCheckerHandler, start_hdlr=None) -> None:
        self.bot        = bot
        self.checker    = checker
        self.start_hdlr = start_hdlr  # set after construction to avoid circular import

    # ─────────────────────────────────────────────────────────────────────────
    # Dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    async def dispatch(self, call: CallbackQuery) -> None:
        data = call.data

        # ── Filter selection ──────────────────────────────────────────────────
        if data.startswith("myntra_filter:"):
            filter_mode = data.split(":", 1)[1]
            await self.checker.handle_filter_selection(call, filter_mode)

        # ── Open checker (from /start or /setkey button) ──────────────────────
        elif data == "myntra_open":
            await self._handle_open(call)

        # ── Stop running loop ─────────────────────────────────────────────────
        elif data == "myntra_stop":
            await self._handle_stop(call)

        # ── 🛒 Buy Next ───────────────────────────────────────────────────────
        elif data.startswith("myntra_next:"):
            order_id = data.split(":", 1)[1]
            await self._handle_buy_next(call, order_id)

        # ── ❌ Cancel Purchase ─────────────────────────────────────────────────
        elif data.startswith("myntra_cancel:"):
            order_id = data.split(":", 1)[1]
            await self._handle_cancel(call, order_id)

        # ── 🔄 Refresh SMS ────────────────────────────────────────────────────
        elif data.startswith("myntra_refresh:"):
            order_id = data.split(":", 1)[1]
            await self._handle_refresh(call, order_id)

        # ── 🔙 Back to filter menu ────────────────────────────────────────────
        elif data == "myntra_menu":
            await self._handle_menu(call)

        # ── 📊 Stats card (from /start message) ──────────────────────────────
        elif data == "myntra_stats_card":
            await self._handle_stats_card(call)

        # ── 🗑 Delete key prompt (from /start) ────────────────────────────────
        elif data == "myntra_delkey_prompt":
            await self._handle_delkey_prompt(call)

        elif data == "myntra_delkey_confirm":
            await self._handle_delkey_confirm(call)

        elif data == "myntra_delkey_cancel":
            await self._handle_delkey_cancel(call)

        # ── 🔑 Set API key prompt / cancel ────────────────────────────────────
        elif data == "myntra_setkey_prompt":
            await self.start_hdlr.show_key_prompt_callback(
                call.from_user.id,
                call.message.chat.id,
                call.message.message_id,
            )
            await self.bot.answer_callback_query(call.id)

        elif data == "myntra_setkey_cancel":
            await self.start_hdlr.cancel_key_prompt(
                call.from_user.id,
                call.message.chat.id,
                call.message.message_id,
            )
            await self.bot.answer_callback_query(call.id)

        # Backwards compat — old help_key button
        elif data == "myntra_help_key":
            await self.bot.answer_callback_query(
                call.id,
                "🔑 Tap 'Set Api Key' From The Main Menu And Send Your nxn_ Key",
                show_alert=True,
            )

        # ── Copy buttons ───────────────────────────────────────────────────────
        # Both Copy Code and Copy Full SMS now use native CopyTextButton — no callbacks fire
        else:
            await self.bot.answer_callback_query(call.id, "⚠️ Unknown Action")

    # ─────────────────────────────────────────────────────────────────────────
    # 📋 Copy Code / Copy Full SMS
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_copy(self, call: CallbackQuery, order_id: str, kind: str) -> None:
        """Show code or full SMS as alert — user can long-press to copy."""
        try:
            from core.sms_poller import _sms_store
            sms_data = _sms_store.get(order_id, {})

            if kind == "code":
                text = sms_data.get("code", "")
                if not text:
                    order = await user_store.get_last_order(call.from_user.id)
                    text  = order.get("last_otp", "")
                await self.bot.answer_callback_query(
                    call.id,
                    text=f"\U0001f510 {text}" if text else "\u26a0\ufe0f Code Not Found",
                    show_alert=True,
                )
            else:
                text = sms_data.get("full_sms", "")
                if not text:
                    order = await user_store.get_last_order(call.from_user.id)
                    text  = order.get("last_full_sms", "")
                # Telegram answer_callback_query limit is 200 chars — truncate gracefully
                if text and len(text) > 196:
                    text = text[:196] + "…"
                await self.bot.answer_callback_query(
                    call.id,
                    text=text if text else "\u26a0\ufe0f Sms Text Not Found",
                    show_alert=True,
                )
        except Exception as exc:
            logger.warning("[Copy] _handle_copy failed order=%s kind=%s: %s", order_id, kind, exc)
            try:
                await self.bot.answer_callback_query(call.id, "\u26a0\ufe0f Copy Failed", show_alert=False)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # 📦 Open checker
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_open(self, call: CallbackQuery) -> None:
        """Edit the /start message → checker filter menu."""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(
                call.id, "⚠️ No Api Key — Tap 🔑 Set Api Key From The Main Menu", show_alert=True
            )
            return

        await self.bot.answer_callback_query(call.id)

        # Stop any running loop on the previous session message
        await self.checker._stop_session(user_id, cancel_pending=False)

        # Persist new session message coordinates
        await user_store.update_order(user_id, {
            "message_id": msg_id,
            "chat_id":    chat_id,
            "status":     "IDLE",
        })

        await self.checker.show_filter_menu(chat_id, msg_id, user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # ⛔ Stop Loop
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_stop(self, call: CallbackQuery) -> None:
        user_id = call.from_user.id
        await self.bot.answer_callback_query(call.id, f"⛔ {sc('Stopping…')}")
        await self.checker._stop_session(user_id, cancel_pending=True)
        # _on_task_done will edit the message to stopped state

    # ─────────────────────────────────────────────────────────────────────────
    # 🛒 Buy Next  (cancel current → restart loop with same filter)
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_buy_next(
        self, call: CallbackQuery, old_order_id: str
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(call.id, "⚠️ No Api Key", show_alert=True)
            return

        await self.bot.answer_callback_query(call.id, f"🛒  {sc('Buying Next…')}")

        # Stop SMS poller for the old order
        from core.sms_poller import stop_sms_poller
        stop_sms_poller(user_id)

        # Schedule deferred cancel on the OLD order (non-blocking)
        if old_order_id:
            schedule_deferred_cancel(api_key, old_order_id)

        # Retrieve last-used filter
        filter_mode = await user_store.get_preference(user_id, "filter", "ANY")

        # ── Send a NEW message (old result card stays visible) ────────────────
        new_msg = await self.bot.send_message(
            chat_id=chat_id,
            text=f"⏳  <b>{sc('Starting Next Check…')}</b>",
            parse_mode="HTML",
        )
        new_msg_id = new_msg.message_id

        # Persist new message coords so all edits land on the new message
        await user_store.update_order(user_id, {
            "message_id": new_msg_id,
            "chat_id":    chat_id,
        })

        await self.checker.restart_loop(user_id, chat_id, new_msg_id, filter_mode, api_key)

    # ─────────────────────────────────────────────────────────────────────────
    # ❌ Cancel Purchase  (try immediate cancel, fall back to deferred)
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_cancel(
        self, call: CallbackQuery, order_id: str
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        await self.bot.answer_callback_query(call.id, f"⏳  {sc('Cancelling…')}")

        if not api_key:
            return

        # Stop SMS poller + any running loop
        from core.sms_poller import stop_sms_poller, _result_markup_no_cancel, _sms_notification_text, _sms_msg_markup, _sms_store
        stop_sms_poller(user_id)
        await self.checker._stop_session(user_id, cancel_pending=False)

        order   = await user_store.get_last_order(user_id)
        number  = order.get("number",  "")
        attempt = order.get("attempt", 1)
        cost    = order.get("cost",    0)
        myn_status = order.get("status", "REGISTERED")

        # ── Try immediate cancel ───────────────────────────────────────────────
        cancel_result = await try_immediate_cancel(api_key, order_id)

        # ── BAD_STATUS → order is in final state → check if OTP was received ──
        if cancel_result in NexNumStatus.CANCEL_TERMINAL:
            logger.info("[Cancel] BAD_STATUS on %s — fetching getStatus to check for OTP", order_id)
            status_res = await nexnum_client.get_status(api_key, order_id)
            otp_code   = status_res.get("code",     "").strip()
            full_sms   = status_res.get("full_sms", "").strip()
            sender     = status_res.get("sender",   "").strip()

            if otp_code:
                # OTP was already received — show it, don't show cancel screen
                logger.info("[Cancel] OTP=%s found on BAD_STATUS order=%s — showing OTP", otp_code, order_id)
                _sms_store[order_id] = {"code": otp_code, "full_sms": full_sms}

                # Edit result card with OTP + remove Cancel button
                try:
                    await safe_edit(
                        self.bot, chat_id, msg_id,
                        build_result_card(number, myn_status, order_id, attempt, cost, otp_code),
                        _result_markup_no_cancel(order_id),
                    )
                except Exception as e:
                    logger.warning("[Cancel] edit result card failed: %s", e)

                # Send full SMS notification as reply
                try:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=_sms_notification_text(number, otp_code, full_sms, sender, [otp_code]),
                        parse_mode="HTML",
                        reply_to_message_id=msg_id,
                        reply_markup=_sms_msg_markup(order_id, otp_code, full_sms),
                    )
                except Exception as e:
                    logger.warning("[Cancel] send OTP message failed: %s", e)
                return  # ← Don't show cancel screen

            else:
                # No OTP — order is genuinely done (completed or cancelled elsewhere)
                await user_store.update_order(user_id, {"status": "REFUNDED"})
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_refunded_card(number, order_id, attempt, cost),
                    _refunded_markup(order_id),
                )
                return

        # ── Normal cancel (immediate success or deferred) ─────────────────────
        await user_store.update_order(user_id, {"status": "REFUNDED"})

        immediate_ok = cancel_result is True
        suffix = "" if immediate_ok else f"\n<code>({sc('Refund Queued — Processed Within 60s')})</code>"
        await safe_edit(
            self.bot, chat_id, msg_id,
            build_refunded_card(number, order_id, attempt, cost) + suffix,
            _refunded_markup(order_id),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 🔄 Refresh SMS  (poll NexNum getStatus for OTP)
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_refresh(
        self, call: CallbackQuery, order_id: str
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(call.id, "⚠️ No Api Key", show_alert=True)
            return

        # Ack the button tap immediately (Telegram requires this within 5s)
        await self.bot.answer_callback_query(call.id, f"🔄  {sc('Refreshing…')}")

        status_res = await nexnum_client.get_status(api_key, order_id)
        raw_status = status_res.get("status", "")
        otp_code   = status_res.get("code",     "").strip()
        full_sms   = status_res.get("full_sms", "").strip()
        sender     = status_res.get("sender",   "").strip()

        order       = await user_store.get_last_order(user_id)
        number      = order.get("number",     "")
        attempt     = order.get("attempt",    1)
        # Read myn_result (REGISTERED/NOT_REGISTERED) — stored once at match time,
        # never overwritten by lifecycle changes (CHECKING → COMPLETED).
        # Falls back gracefully if field is missing (old orders).
        myn_status  = order.get("myn_result") or order.get("status", "REGISTERED")
        if myn_status not in ("REGISTERED", "NOT_REGISTERED"):
            myn_status = "REGISTERED"
        cost        = order.get("cost", 0)

        if raw_status == "STATUS_OK" and otp_code:
            # ── 1. Edit result card to show OTP (Cancel button removed) ──────
            from core.sms_poller import _result_markup_no_cancel, _sms_store
            # Check if poller already delivered this exact code — prevents duplicate
            # notifications when the user taps Refresh right after auto-send fires.
            already_notified = _sms_store.get(order_id, {}).get("code") == otp_code

            _sms_store[order_id] = {"code": otp_code, "full_sms": full_sms}
            await safe_edit(
                self.bot, chat_id, msg_id,
                build_result_card(number, myn_status, order_id, attempt, cost, otp_code),
                _result_markup_no_cancel(order_id),
            )
            # Persist OTP — myn_result field is intentionally NOT touched here
            await user_store.update_order(user_id, {
                "last_otp":      otp_code,
                "last_full_sms": full_sms,
                "status":        "COMPLETED",
            })

            # ── 2. Send SMS notification ONLY if poller hasn't sent it already ─
            if not already_notified:
                from core.sms_poller import _sms_notification_text, _sms_msg_markup
                try:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=_sms_notification_text(number, otp_code, full_sms, sender, [otp_code]),
                        parse_mode="HTML",
                        reply_to_message_id=msg_id,
                        reply_markup=_sms_msg_markup(order_id, otp_code, full_sms),
                    )
                except Exception as e:
                    logger.warning("[Refresh] send_message failed: %s", e)
            else:
                logger.info("[Refresh] skipped duplicate notify code=%s order=%s", otp_code, order_id)

        elif raw_status in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY"):
            # Already answered above — send a follow-up message so user sees feedback
            try:
                sent = await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏳  <b>{sc('Still Waiting For Sms…')}</b>",
                    parse_mode="HTML",
                    reply_to_message_id=msg_id,
                )
                # Auto-delete after 5s so chat stays clean
                import asyncio as _asyncio
                async def _delete_later(bot, cid, mid, delay=5):
                    await _asyncio.sleep(delay)
                    try: await bot.delete_message(cid, mid)
                    except Exception: pass
                _asyncio.create_task(_delete_later(self.bot, chat_id, sent.message_id))
            except Exception as e:
                logger.warning("[Refresh] wait status send failed: %s", e)

        elif raw_status in ("ACCESS_CANCEL", "STATUS_CANCEL"):
            await safe_edit(
                self.bot, chat_id, msg_id,
                f"❌  <b>{sc('Order Already Cancelled')}</b>\n\n"
                f"<blockquote><code>[{raw_status}]</code></blockquote>",
                _refunded_markup(),
            )

        elif not status_res.get("ok"):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️  {sc('Error')}: <code>{status_res.get('error', 'unknown')}</code>",
                    parse_mode="HTML",
                    reply_to_message_id=msg_id,
                )
            except Exception:
                pass

        else:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️  {sc('Status')}: <code>{raw_status or 'unknown'}</code>",
                    parse_mode="HTML",
                    reply_to_message_id=msg_id,
                )
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # 🔙 Back to Filter Menu
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_menu(self, call: CallbackQuery) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        await self.bot.answer_callback_query(call.id)
        # Stop any loop (safety — shouldn't be running at this point)
        await self.checker._stop_session(user_id, cancel_pending=False)
        await self.checker.show_filter_menu(chat_id, msg_id, user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 📊 Stats card (edits /start message)
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_stats_card(self, call: CallbackQuery) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        await self.bot.answer_callback_query(call.id)

        stats   = await user_store.get_stats(user_id)
        balance = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        # Back button
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"🏠  {sc('Back')}", callback_data="myntra_delkey_cancel"))

        await safe_edit(
            self.bot, chat_id, msg_id,
            build_stats_msg(stats, balance),
            kb,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 🗑 Delete Key — prompt + confirm
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_delkey_prompt(self, call: CallbackQuery) -> None:
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        await self.bot.answer_callback_query(call.id)

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(f"✅  {sc('Yes, Delete')}", callback_data="myntra_delkey_confirm"),
            InlineKeyboardButton(f"❌  {sc('Cancel')}",      callback_data="myntra_delkey_cancel"),
        )
        await safe_edit(
            self.bot, chat_id, msg_id,
            f"🗑  <b>{sc('Delete Api Key?')}</b>\n\n"
            f"<blockquote>{sc('This Will Remove Your Saved NexNum Api Key.')}\n"
            f"{sc('You Can Add A New Key Anytime From The Main Menu.')}</blockquote>",
            kb,
        )

    async def _handle_delkey_confirm(self, call: CallbackQuery) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id

        await self.bot.answer_callback_query(call.id, f"🗑  {sc('Key Deleted')}")
        await user_store.delete_api_key(user_id)

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            f"🔑  {sc('Set New Key')}",
            callback_data="myntra_setkey_prompt"
        ))
        await safe_edit(
            self.bot, chat_id, msg_id,
            f"🗑  <b>{sc('Api Key Removed')}</b>\n\n"
            f"<blockquote>{sc('Your Api Key Has Been Deleted.')}</blockquote>",
            kb,
        )

    async def _handle_delkey_cancel(self, call: CallbackQuery) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        await self.bot.answer_callback_query(call.id)

        # Restore welcome screen
        balance = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            f"📦  {sc('Myntra Checker')}", callback_data="myntra_open"
        ))
        kb.row(
            InlineKeyboardButton(f"📊  {sc('My Stats')}",  callback_data="myntra_stats_card"),
            InlineKeyboardButton(f"🗑  {sc('Del Key')}",   callback_data="myntra_delkey_prompt"),
        )
        await safe_edit(
            self.bot, chat_id, msg_id,
            build_welcome_msg(bool(api_key), balance),
            kb,
        )
