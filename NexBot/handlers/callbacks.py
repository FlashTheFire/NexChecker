"""NexBot — Inline callback dispatcher.

Callback data format (new, unified):
  nex:<action>:<platform_key>           → nex:stop:myntra
  nex:<action>:<platform_key>:<order>   → nex:cancel:myntra:ORDER_ID

Backward compat (old `myntra_` prefix): all old-style callbacks are mapped to
the Myntra handler so active buttons from in-flight sessions keep working.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict

from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.nexnum_api import nexnum_client, NexNumStatus
from core import user_store
from utils.formatting import (
    sc, build_refunded_card, build_result_card,
    build_stats_msg, build_welcome_msg,
)
from handlers.checker import (
    CheckerHandler,
    schedule_deferred_cancel, try_immediate_cancel,
    make_result_markup, make_refunded_markup, make_stopped_markup,
    make_back_markup, safe_edit,
)

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Routes inline keyboard callbacks to the correct CheckerHandler."""

    def __init__(
        self,
        bot:      AsyncTeleBot,
        checkers: Dict[str, CheckerHandler],
        start_hdlr = None,
    ) -> None:
        self.bot        = bot
        self.checkers   = checkers          # {"myntra": ..., "bigbasket": ...}
        self.start_hdlr = start_hdlr        # set after construction to avoid circular import

    def _get_checker(self, platform_key: str) -> CheckerHandler | None:
        """Return the CheckerHandler for a platform key, or None if unknown."""
        ch = self.checkers.get(platform_key)
        if ch is None:
            logger.warning("[Callbacks] unknown platform_key=%r — ignored", platform_key)
        return ch

    # ─────────────────────────────────────────────────────────────────────────
    # Dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    async def dispatch(self, call: CallbackQuery) -> None:
        data = call.data or ""

        # ── NEW unified format: nex:<action>:<platform>[:<order_id>] ──────────
        if data.startswith("nex:"):
            await self._dispatch_nex(call, data)
            return

        # ── LEGACY backward-compat: myntra_* callbacks ────────────────────────
        await self._dispatch_legacy(call, data)

    # ── Unified nex: dispatcher ───────────────────────────────────────────────

    async def _dispatch_nex(self, call: CallbackQuery, data: str) -> None:
        """Handle nex:<action>:<platform>[:<order_id>] callbacks."""
        parts = data.split(":", 3)
        # parts[0] = "nex", parts[1] = action, parts[2] = platform_key, parts[3] = optional extra
        if len(parts) < 3:
            await self.bot.answer_callback_query(call.id, "⚠️ Malformed callback")
            return

        action   = parts[1]
        pkey     = parts[2]
        extra    = parts[3] if len(parts) > 3 else ""
        checker  = self._get_checker(pkey)

        if action == "filter":
            if checker:
                await checker.handle_filter_selection(call, extra)

        elif action == "open":
            if checker:
                await self._handle_open(call, checker)

        elif action == "stop":
            if checker:
                await self._handle_stop(call, checker)

        elif action == "next":
            if checker:
                await self._handle_buy_next(call, extra, checker)

        elif action == "cancel":
            if checker:
                await self._handle_cancel(call, extra, checker)

        elif action == "refresh":
            if checker:
                await self._handle_refresh(call, extra, checker)

        elif action == "menu":
            if checker:
                await self._handle_menu(call, checker)

        elif action == "copy":
            # nex:copy:<platform>:<order_id>:<kind>  — split on kind separately
            # data = nex:copy:<pkey>:<order_id>:<kind>
            sub_parts = data.split(":", 4)
            order_id  = sub_parts[3] if len(sub_parts) > 3 else ""
            kind      = sub_parts[4] if len(sub_parts) > 4 else ""
            await self._handle_copy(call, order_id, kind)

        # ── Global actions (no platform-specific routing needed) ──────────────
        elif action == "stats_card":
            await self._handle_stats_card(call, pkey)

        elif action == "delkey_prompt":
            await self._handle_delkey_prompt(call, pkey)

        elif action == "delkey_cancel":
            await self._handle_delkey_cancel(call)

        elif action == "delkey_confirm":
            await self._handle_delkey_confirm(call, pkey)

        elif action in ("setkey_prompt", "setkey_cancel"):
            # These are global (not platform-specific) — just forward to start_hdlr
            if action == "setkey_prompt":
                await self.start_hdlr.show_key_prompt_callback(
                    call.from_user.id, call.message.chat.id, call.message.message_id,
                )
            else:
                await self.start_hdlr.cancel_key_prompt(
                    call.from_user.id, call.message.chat.id, call.message.message_id,
                )
            await self.bot.answer_callback_query(call.id)

        else:
            await self.bot.answer_callback_query(call.id, "⚠️ Unknown Action")

    # ── Legacy myntra_* dispatcher (backward compat) ──────────────────────────

    async def _dispatch_legacy(self, call: CallbackQuery, data: str) -> None:
        """Handle old-style myntra_* callback_data from in-flight messages."""
        checker = self._get_checker("myntra")

        if data.startswith("myntra_filter:"):
            filter_mode = data.split(":", 1)[1]
            if checker:
                await checker.handle_filter_selection(call, filter_mode)

        elif data == "myntra_open":
            if checker:
                await self._handle_open(call, checker)

        elif data == "myntra_stop":
            if checker:
                await self._handle_stop(call, checker)

        elif data.startswith("myntra_next:"):
            order_id = data.split(":", 1)[1]
            if checker:
                await self._handle_buy_next(call, order_id, checker)

        elif data.startswith("myntra_cancel:"):
            order_id = data.split(":", 1)[1]
            if checker:
                await self._handle_cancel(call, order_id, checker)

        elif data.startswith("myntra_refresh:"):
            order_id = data.split(":", 1)[1]
            if checker:
                await self._handle_refresh(call, order_id, checker)

        elif data == "myntra_menu":
            if checker:
                await self._handle_menu(call, checker)

        elif data == "myntra_stats_card":
            await self._handle_stats_card(call, "myntra")

        elif data == "myntra_delkey_prompt":
            await self._handle_delkey_prompt(call, "myntra")

        elif data == "myntra_delkey_confirm":
            await self._handle_delkey_confirm(call, "myntra")

        elif data == "myntra_delkey_cancel":
            await self._handle_delkey_cancel(call)

        elif data == "myntra_setkey_prompt":
            await self.start_hdlr.show_key_prompt_callback(
                call.from_user.id, call.message.chat.id, call.message.message_id,
            )
            await self.bot.answer_callback_query(call.id)

        elif data == "myntra_setkey_cancel":
            await self.start_hdlr.cancel_key_prompt(
                call.from_user.id, call.message.chat.id, call.message.message_id,
            )
            await self.bot.answer_callback_query(call.id)

        elif data == "myntra_help_key":
            await self.bot.answer_callback_query(
                call.id,
                "🔑 Tap 'Set Api Key' From The Main Menu And Send Your nxn_ Key",
                show_alert=True,
            )

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

    async def _handle_open(self, call: CallbackQuery, checker: CheckerHandler) -> None:
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
        await checker._stop_session(user_id, cancel_pending=False)
        await user_store.update_order(user_id, {
            "platform":   checker.pkey,
            "message_id": msg_id,
            "chat_id":    chat_id,
            "status":     "IDLE",
        })
        await checker.show_filter_menu(chat_id, msg_id, user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # ⛔ Stop Loop
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_stop(self, call: CallbackQuery, checker: CheckerHandler) -> None:
        user_id = call.from_user.id
        await self.bot.answer_callback_query(call.id, f"⛔ {sc('Stopping…')}")
        await checker._stop_session(user_id, cancel_pending=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 🛒 Buy Next
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_buy_next(
        self, call: CallbackQuery, old_order_id: str, checker: CheckerHandler
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(call.id, "⚠️ No Api Key", show_alert=True)
            return

        await self.bot.answer_callback_query(call.id, f"🛒  {sc('Buying Next…')}")

        from core.sms_poller import stop_sms_poller
        stop_sms_poller(user_id)

        if old_order_id:
            schedule_deferred_cancel(api_key, old_order_id)

        filter_mode = await user_store.get_preference(user_id, f"filter_{checker.pkey}", "ANY")

        # Send a NEW message (old result card stays visible)
        new_msg = await self.bot.send_message(
            chat_id=chat_id,
            text=f"⏳  <b>{sc('Starting Next Check…')}</b>",
            parse_mode="HTML",
        )
        new_msg_id = new_msg.message_id

        await user_store.update_order(user_id, {
            "platform":   checker.pkey,
            "message_id": new_msg_id,
            "chat_id":    chat_id,
        })
        await checker.restart_loop(user_id, chat_id, new_msg_id, filter_mode, api_key)

    # ─────────────────────────────────────────────────────────────────────────
    # ❌ Cancel Purchase
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_cancel(
        self, call: CallbackQuery, order_id: str, checker: CheckerHandler
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        await self.bot.answer_callback_query(call.id, f"⏳  {sc('Cancelling…')}")

        if not api_key:
            return

        from core.sms_poller import stop_sms_poller, _result_markup_no_cancel, _sms_notification_text, _sms_msg_markup, _sms_store
        stop_sms_poller(user_id)
        await checker._stop_session(user_id, cancel_pending=False)

        order      = await user_store.get_last_order(user_id)
        number     = order.get("number",  "")
        attempt    = order.get("attempt", 1)
        cost       = order.get("cost",    0)
        myn_status = order.get("status", "REGISTERED")

        from utils.platforms import get_platform
        platform = get_platform(checker.pkey)

        cancel_result = await try_immediate_cancel(api_key, order_id)

        # BAD_STATUS → order is in final state → check if OTP was received
        if cancel_result in NexNumStatus.CANCEL_TERMINAL:
            logger.info("[Cancel] BAD_STATUS on %s — fetching getStatus to check for OTP", order_id)
            status_res = await nexnum_client.get_status(api_key, order_id)
            otp_code   = status_res.get("code",     "").strip()
            full_sms   = status_res.get("full_sms", "").strip()
            sender     = status_res.get("sender",   "").strip()

            if otp_code:
                logger.info("[Cancel] OTP=%s found on BAD_STATUS order=%s — showing OTP", otp_code, order_id)
                _sms_store[order_id] = {"code": otp_code, "full_sms": full_sms}
                try:
                    await safe_edit(
                        self.bot, chat_id, msg_id,
                        build_result_card(number, myn_status, order_id, attempt, cost, otp_code, platform=platform),
                        _result_markup_no_cancel(order_id, checker.pkey),
                    )
                except Exception as e:
                    logger.warning("[Cancel] edit result card failed: %s", e)
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
                return

            else:
                await user_store.update_order(user_id, {"status": "REFUNDED"})
                await safe_edit(
                    self.bot, chat_id, msg_id,
                    build_refunded_card(number, order_id, attempt, cost, platform=platform),
                    make_refunded_markup(checker.pkey, order_id),
                )
                return

        # Normal cancel
        await user_store.update_order(user_id, {"status": "REFUNDED"})
        immediate_ok = cancel_result is True
        suffix = "" if immediate_ok else f"\n<code>({sc('Refund Queued — Processed Within 60s')})</code>"
        await safe_edit(
            self.bot, chat_id, msg_id,
            build_refunded_card(number, order_id, attempt, cost, platform=platform) + suffix,
            make_refunded_markup(checker.pkey, order_id),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 🔄 Refresh SMS
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_refresh(
        self, call: CallbackQuery, order_id: str, checker: CheckerHandler
    ) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        if not api_key:
            await self.bot.answer_callback_query(call.id, "⚠️ No Api Key", show_alert=True)
            return

        await self.bot.answer_callback_query(call.id, f"🔄  {sc('Refreshing…')}")

        status_res = await nexnum_client.get_status(api_key, order_id)
        raw_status = status_res.get("status", "")
        otp_code   = status_res.get("code",     "").strip()
        full_sms   = status_res.get("full_sms", "").strip()
        sender     = status_res.get("sender",   "").strip()

        order      = await user_store.get_last_order(user_id)
        number     = order.get("number",  "")
        attempt    = order.get("attempt", 1)
        myn_status = order.get("myn_result") or order.get("status", "REGISTERED")
        if myn_status not in ("REGISTERED", "NOT_REGISTERED"):
            myn_status = "REGISTERED"
        cost       = order.get("cost", 0)

        from utils.platforms import get_platform
        from core.sms_poller import _result_markup_no_cancel, _sms_store, _sms_notification_text, _sms_msg_markup
        platform = get_platform(checker.pkey)

        if raw_status == "STATUS_OK" and otp_code:
            _sms_store[order_id] = {"code": otp_code, "full_sms": full_sms}
            await safe_edit(
                self.bot, chat_id, msg_id,
                build_result_card(number, myn_status, order_id, attempt, cost, otp_code, platform=platform),
                _result_markup_no_cancel(order_id, checker.pkey),
            )
            await user_store.update_order(user_id, {
                "last_otp":      otp_code,
                "last_full_sms": full_sms,
                "status":        "COMPLETED",
            })
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

        elif raw_status in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY"):
            try:
                sent = await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏳  <b>{sc('Still Waiting For Sms…')}</b>",
                    parse_mode="HTML",
                    reply_to_message_id=msg_id,
                )
                async def _delete_later(bot, cid, mid, delay=5):
                    await asyncio.sleep(delay)
                    try: await bot.delete_message(cid, mid)
                    except Exception: pass
                asyncio.create_task(_delete_later(self.bot, chat_id, sent.message_id))
            except Exception as e:
                logger.warning("[Refresh] wait status send failed: %s", e)

        elif raw_status in ("ACCESS_CANCEL", "STATUS_CANCEL"):
            await safe_edit(
                self.bot, chat_id, msg_id,
                f"❌  <b>{sc('Order Already Cancelled')}</b>\n\n"
                f"<blockquote><code>[{raw_status}]</code></blockquote>",
                make_refunded_markup(checker.pkey),
            )

        elif not status_res.get("ok"):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️  {sc('Error')}: <code>{status_res.get('error', 'unknown')}</code>",
                    parse_mode="HTML", reply_to_message_id=msg_id,
                )
            except Exception:
                pass
        else:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️  {sc('Status')}: <code>{raw_status or 'unknown'}</code>",
                    parse_mode="HTML", reply_to_message_id=msg_id,
                )
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # 🔙 Back to Filter Menu
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_menu(self, call: CallbackQuery, checker: CheckerHandler) -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        await self.bot.answer_callback_query(call.id)
        await checker._stop_session(user_id, cancel_pending=False)
        await checker.show_filter_menu(chat_id, msg_id, user_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 📊 Stats card
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_stats_card(self, call: CallbackQuery, pkey: str = "myntra") -> None:
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

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"🏠  {sc('Back')}", callback_data=f"nex:delkey_cancel:{pkey}"))

        await safe_edit(self.bot, chat_id, msg_id, build_stats_msg(stats, balance), kb)

    # ─────────────────────────────────────────────────────────────────────────
    # 🗑 Delete Key — prompt + confirm
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_delkey_prompt(self, call: CallbackQuery, pkey: str = "myntra") -> None:
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        await self.bot.answer_callback_query(call.id)

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(f"✅  {sc('Yes, Delete')}", callback_data=f"nex:delkey_confirm:{pkey}"),
            InlineKeyboardButton(f"❌  {sc('Cancel')}",      callback_data=f"nex:delkey_cancel:{pkey}"),
        )
        await safe_edit(
            self.bot, chat_id, msg_id,
            f"🗑  <b>{sc('Delete Api Key?')}</b>\n\n"
            f"<blockquote>{sc('This Will Remove Your Saved NexNum Api Key.')}\n"
            f"{sc('You Can Add A New Key Anytime From The Main Menu.')}</blockquote>",
            kb,
        )

    async def _handle_delkey_confirm(self, call: CallbackQuery, pkey: str = "myntra") -> None:
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id

        await self.bot.answer_callback_query(call.id, f"🗑  {sc('Key Deleted')}")
        await user_store.delete_api_key(user_id)

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            f"🔑  {sc('Set New Key')}",
            callback_data=f"nex:setkey_prompt:{pkey}"
        ))
        await safe_edit(
            self.bot, chat_id, msg_id,
            f"🗑  <b>{sc('Api Key Removed')}</b>\n\n"
            f"<blockquote>{sc('Your Api Key Has Been Deleted.')}</blockquote>",
            kb,
        )

    async def _handle_delkey_cancel(self, call: CallbackQuery) -> None:
        """Restore home screen (welcome card)."""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        msg_id  = call.message.message_id
        api_key = await user_store.get_api_key(user_id)

        await self.bot.answer_callback_query(call.id)

        balance = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        from handlers.start import _home_markup
        await safe_edit(
            self.bot, chat_id, msg_id,
            build_welcome_msg(bool(api_key), balance),
            _home_markup(bool(api_key)),
        )
