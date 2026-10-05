"""NexBot — /start, /setkey, /mystats, /delkey, /help + API key flow handler.

API Key Flow (button-based, no commands needed):
  1. /start or [🔑 Set API Key] button → prompt screen
  2. User sends any text matching nxn_... → auto-detect, save, delete msg, success
  3. If user sends something else while waiting → ignore / re-prompt
  4. [🗑 Delete Key] → confirm prompt → delete → success → back to welcome

State: _waiting_key = {user_id: wait_msg_id} tracks who we're waiting a key from.
"""
from __future__ import annotations

import logging
import re

from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, Message
)

from core.nexnum_api import nexnum_client
from core import user_store
from utils.formatting import (
    sc, build_welcome_msg, build_stats_msg, format_balance
)

logger = logging.getLogger(__name__)

# Pattern: NexNum API keys start with nxn_ followed by alphanumerics
_NEXNUM_KEY_RE = re.compile(r"^nxn_[A-Za-z0-9_\-]{10,}$")

# {user_id: prompt_message_id} — we're waiting for the user to send their key
_waiting_key: dict[int, int] = {}


class StartHandler:
    def __init__(self, bot: AsyncTeleBot) -> None:
        self.bot = bot

    # ── Welcome screen ────────────────────────────────────────────────────────

    async def handle_start(self, message: Message) -> None:
        user_id = message.from_user.id
        chat_id = message.chat.id
        api_key = await user_store.get_api_key(user_id)

        balance: float | None = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        await self.bot.send_message(
            chat_id,
            build_welcome_msg(bool(api_key), balance),
            reply_markup=_home_markup(bool(api_key)),
            parse_mode="HTML",
        )

    # ── /setkey shortcut → trigger key prompt ────────────────────────────────

    async def handle_setkey(self, message: Message) -> None:
        """If key given inline (/setkey nxn_xxx), process directly.
        Otherwise, show the prompt screen (same as button flow).
        """
        user_id = message.from_user.id
        chat_id = message.chat.id
        parts   = message.text.strip().split(maxsplit=1)

        if len(parts) >= 2 and parts[1].strip():
            # Inline: /setkey nxn_xxx — validate + save immediately
            api_key = parts[1].strip()
            # Try to delete the command message (contains the key)
            try:
                await self.bot.delete_message(chat_id, message.message_id)
            except Exception:
                pass
            await self._validate_and_save(user_id, chat_id, api_key, reply_to=None)
        else:
            # No key given — show the interactive prompt
            await self._show_key_prompt(user_id, chat_id)

    # ── Key prompt screen ─────────────────────────────────────────────────────

    async def show_key_prompt_callback(self, user_id: int, chat_id: int, msg_id: int) -> None:
        """Called from CallbackHandler when [🔑 Set API Key] is tapped.
        Edits the existing message to the prompt screen.
        """
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"❌  {sc('Cancel')}", callback_data="myntra_setkey_cancel"))

        prompt_text = (
            f"<blockquote><b>🔑 {sc('Set Api Key')}</b></blockquote>\n\n"
            f"📨  {sc('Send Your NexNum Api Key As A Message')}:\n\n"
            f"<code>nxn_live_xxxxxxxxxxxxxxxxxxxxxxx</code>\n\n"
            f"<blockquote>{sc('Get Your Key At')}\n"
            f"nexnum.in/en/dashboard/settings\n\n"
            f"⚠️  {sc('Your Message Will Be Deleted Automatically For Security.')}</blockquote>"
        )

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=prompt_text,
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            # Fallback: send new
            sent = await self.bot.send_message(chat_id, prompt_text, reply_markup=kb, parse_mode="HTML")
            msg_id = sent.message_id

        _waiting_key[user_id] = msg_id

    async def _show_key_prompt(self, user_id: int, chat_id: int) -> None:
        """Send a fresh key prompt message (for /setkey with no args)."""
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"❌  {sc('Cancel')}", callback_data="myntra_setkey_cancel"))

        sent = await self.bot.send_message(
            chat_id,
            f"<blockquote><b>🔑 {sc('Set Api Key')}</b></blockquote>\n\n"
            f"📨  {sc('Send Your NexNum Api Key As A Message')}:\n\n"
            f"<code>nxn_live_xxxxxxxxxxxxxxxxxxxxxxx</code>\n\n"
            f"<blockquote>{sc('Get Your Key At')}\n"
            f"nexnum.in/en/dashboard/settings\n\n"
            f"⚠️  {sc('Your Message Will Be Deleted Automatically For Security.')}</blockquote>",
            reply_markup=kb,
            parse_mode="HTML",
        )
        _waiting_key[user_id] = sent.message_id

    # ── Incoming message handler (called from bot.py for ALL text messages) ───

    async def handle_text_message(self, message: Message) -> bool:
        """Try to intercept the message as an API key input.

        Returns True if handled (suppress further processing), False otherwise.
        """
        user_id = message.from_user.id
        chat_id = message.chat.id
        text    = (message.text or "").strip()

        # Not waiting for a key from this user
        if user_id not in _waiting_key:
            return False

        prompt_msg_id = _waiting_key[user_id]

        # Always delete the user's message immediately (contains sensitive key)
        try:
            await self.bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass

        if _NEXNUM_KEY_RE.match(text):
            # Valid key format — validate + save
            del _waiting_key[user_id]
            await self._validate_and_save(user_id, chat_id, text, reply_to=prompt_msg_id)
        else:
            # Wrong format — re-show error on the prompt message
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(f"❌  {sc('Cancel')}", callback_data="myntra_setkey_cancel"))
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prompt_msg_id,
                    text=(
                        f"<blockquote><b>🔑 {sc('Set Api Key')}</b></blockquote>\n\n"
                        f"⚠️  <b>{sc('Invalid Key Format.')}</b>\n"
                        f"{sc('NexNum Keys Start With')} <code>nxn_</code>\n\n"
                        f"📨  {sc('Please Send Your Key Again')}:\n\n"
                        f"<code>nxn_live_xxxxxxxxxxxxxxxxxxxxxxx</code>"
                    ),
                    reply_markup=kb,
                    parse_mode="HTML",
                )
            except Exception:
                pass

        return True

    # ── Validate + save key ───────────────────────────────────────────────────

    async def _validate_and_save(
        self,
        user_id:  int,
        chat_id:  int,
        api_key:  str,
        reply_to: int | None,
    ) -> None:
        """Validate key with NexNum, save on success, show result.

        If reply_to is a message_id, edit that message.
        Otherwise send a new one.
        """
        # Show "validating" in the prompt message
        validating_text = f"⏳  <b>{sc('Validating Api Key…')}</b>"
        kb_cancel       = InlineKeyboardMarkup()
        kb_cancel.add(InlineKeyboardButton(f"❌ {sc('Cancel')}", callback_data="myntra_setkey_cancel"))

        if reply_to:
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id, message_id=reply_to,
                    text=validating_text, parse_mode="HTML", reply_markup=None,
                )
            except Exception:
                reply_to = None

        if not reply_to:
            sent     = await self.bot.send_message(chat_id, validating_text, parse_mode="HTML")
            reply_to = sent.message_id

        # Call NexNum
        bal = await nexnum_client.get_balance(api_key)

        if not bal["ok"]:
            # Invalid key
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(f"🔑  {sc('Try Again')}", callback_data="myntra_setkey_prompt"))
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=reply_to,
                    text=(
                        f"❌  <b>{sc('Invalid Api Key')}</b>\n\n"
                        f"<blockquote>{sc('NexNum Rejected This Key.')}\n"
                        f"<code>{bal.get('error', 'Unknown error')}</code></blockquote>"
                    ),
                    reply_markup=kb,
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        # Save to store
        await user_store.set_api_key(user_id, api_key)

        # Success screen
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton(
            f"📦 {sc('Start Myntra Checker')}", callback_data="myntra_open"
        ))
        kb.row(
            InlineKeyboardButton(f"📊 {sc('My Stats')}",  callback_data="myntra_stats_card"),
            InlineKeyboardButton(f"🗑 {sc('Del Key')}",   callback_data="myntra_delkey_prompt"),
        )

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=reply_to,
                text=(
                    f"<blockquote><b>✅ {sc('Api Key Saved!')}</b></blockquote>\n\n"
                    f"💎  <b>{sc('Balance')}:</b>  <code>{format_balance(bal['balance'])}</code>\n\n"
                    f"<blockquote>🔒 {sc('Your Key Is Stored Securely.')}\n"
                    f"{sc('Tap Below To Start Checking.')}</blockquote>"
                ),
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception:
            pass

    # ── Cancel key prompt (button callback) ───────────────────────────────────

    async def cancel_key_prompt(self, user_id: int, chat_id: int, msg_id: int) -> None:
        """Called from CallbackHandler on 'myntra_setkey_cancel'."""
        _waiting_key.pop(user_id, None)
        api_key = await user_store.get_api_key(user_id)

        balance: float | None = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=build_welcome_msg(bool(api_key), balance),
                reply_markup=_home_markup(bool(api_key)),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # ── /mystats ──────────────────────────────────────────────────────────────

    async def handle_mystats(self, message: Message) -> None:
        user_id = message.from_user.id
        chat_id = message.chat.id
        api_key = await user_store.get_api_key(user_id)

        stats   = await user_store.get_stats(user_id)
        balance = None
        if api_key:
            bal = await nexnum_client.get_balance(api_key)
            if bal["ok"]:
                balance = bal["balance"]

        await self.bot.send_message(
            chat_id, build_stats_msg(stats, balance), parse_mode="HTML",
        )

    # ── /delkey shortcut ──────────────────────────────────────────────────────

    async def handle_delkey(self, message: Message) -> None:
        await user_store.delete_api_key(message.from_user.id)
        await self.bot.send_message(
            message.chat.id,
            f"🗑  <b>{sc('Api Key Removed')}</b>\n\n"
            f"<blockquote>{sc('Your Api Key Has Been Deleted.')}</blockquote>",
            parse_mode="HTML",
        )

    # ── /help ─────────────────────────────────────────────────────────────────

    async def handle_help(self, message: Message) -> None:
        await self.bot.send_message(
            message.chat.id,
            (
                f"<b>🤖 {sc('NexChecker Help')}</b>\n\n"
                f"<b>{sc('How It Works')}:</b>\n"
                f"<blockquote>"
                f"1. {sc('Tap')} <b>🔑 {sc('Set Key')}</b> {sc('From The Main Menu')}\n"
                f"2. {sc('Send Your NexNum Key — It Is Deleted Automatically')}\n"
                f"3. {sc('Tap')} <b>📦 {sc('Myntra Checker')}</b> {sc('And Pick A Filter')}\n"
                f"4. {sc('Bot Buys A')} <code>nl</code> {sc('Number + Hits Myntra Api')}\n"
                f"5. {sc('Auto-Loops Until Your Filter Matches')}\n"
                f"6. {sc('Result Card Shows With Action Buttons')}"
                f"</blockquote>\n\n"
                f"<b>{sc('Filters')}:</b>\n"
                f"✅  {sc('Registered')}  —  {sc('Find A Registered Myntra Account')}\n"
                f"🛑  {sc('Not Registered')}  —  {sc('Find A Fresh Number')}\n"
                f"📊  {sc('Any')}  —  {sc('Show First Result Regardless')}\n\n"
                f"<b>{sc('Result Card Buttons')}:</b>\n"
                f"🛒  <b>{sc('Buy Next')}</b>  —  {sc('Cancel Current, Buy & Check Another')}\n"
                f"🔄  <b>{sc('Refresh Sms')}</b>  —  {sc('Poll NexNum For Otp')}\n"
                f"❌  <b>{sc('Cancel Purchase')}</b>  —  {sc('Refund Current Order')}"
            ),
            parse_mode="HTML",
        )


# ── Home markup (module-level helper) ─────────────────────────────────────────

def _home_markup(has_key: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    if has_key:
        kb.add(InlineKeyboardButton(f"📦  {sc('Myntra Checker')}", callback_data="myntra_open"))
        kb.row(
            InlineKeyboardButton(f"📊  {sc('My Stats')}",  callback_data="myntra_stats_card"),
            InlineKeyboardButton(f"🗑  {sc('Del Key')}",   callback_data="myntra_delkey_prompt"),
        )
    else:
        kb.add(InlineKeyboardButton(f"🔑  {sc('Set Api Key')}", callback_data="myntra_setkey_prompt"))
    return kb
