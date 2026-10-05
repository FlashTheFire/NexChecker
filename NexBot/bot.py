"""NexBot — Entry point.
Run:  python bot.py
"""
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand

from utils.config import BOT_TOKEN
from core.nexnum_api import nexnum_client
from core.myntra_api import myntra_checker
from handlers.start import StartHandler
from handlers.myntra_checker import MyntraCheckerHandler, _active_sessions, _session_tasks
from handlers.callbacks import CallbackHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NexBot")

# ── Bot + handler instances ───────────────────────────────────────────────────
bot        = AsyncTeleBot(BOT_TOKEN, parse_mode="HTML")
start_hdlr = StartHandler(bot)
checker    = MyntraCheckerHandler(bot)
cb_hdlr    = CallbackHandler(bot, checker, start_hdlr=start_hdlr)

# ─────────────────────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
async def cmd_start(msg):   await start_hdlr.handle_start(msg)

@bot.message_handler(commands=["myntra"])
async def cmd_myntra(msg):  await checker.handle_myntra_command(msg)

@bot.message_handler(commands=["mystats"])
async def cmd_stats(msg):   await start_hdlr.handle_mystats(msg)

@bot.message_handler(commands=["help"])
async def cmd_help(msg):    await start_hdlr.handle_help(msg)


# ── Intercept API key input (any plain text while waiting for key) ─────────────
@bot.message_handler(func=lambda m: m.content_type == "text" and not m.text.startswith("/"))
async def catch_text(msg):
    await start_hdlr.handle_text_message(msg)

# ─────────────────────────────────────────────────────────────────────────────
# Callback dispatcher
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data.startswith("myntra_"))
async def cb_myntra(call):
    await cb_hdlr.dispatch(call)


@bot.callback_query_handler(func=lambda c: c.data.startswith("sms_copy_"))
async def cb_sms_copy(call):
    await cb_hdlr.dispatch(call)

# ─────────────────────────────────────────────────────────────────────────────
# Startup / shutdown
# ─────────────────────────────────────────────────────────────────────────────

async def set_commands() -> None:
    await bot.set_my_commands([
        BotCommand("start",   "Start the bot / main menu"),
        BotCommand("myntra",  "Start Myntra registration checker"),
        BotCommand("mystats", "View your check statistics"),
        BotCommand("help",    "Show help & usage"),
    ])


async def on_shutdown() -> None:
    """Graceful shutdown — cancel tasks, close sessions, save state."""
    logger.info("⏹  Shutting down NexBot…")

    # 1. Stop Telegram polling so no new updates arrive
    try:
        await bot.close_session()
    except Exception:
        pass

    # 2. Cancel all active checker session tasks
    logger.info("Cancelling %d active session(s)…", len(_session_tasks))
    for uid, task in list(_session_tasks.items()):
        if task and not task.done():
            task.cancel()
    if _session_tasks:
        await asyncio.gather(*_session_tasks.values(), return_exceptions=True)
    _active_sessions.clear()
    _session_tasks.clear()

    # 3. Cancel all SMS pollers
    try:
        from core.sms_poller import _sms_pollers
        for uid, task in list(_sms_pollers.items()):
            if task and not task.done():
                task.cancel()
        if _sms_pollers:
            await asyncio.gather(*_sms_pollers.values(), return_exceptions=True)
        _sms_pollers.clear()
    except Exception:
        pass

    # 4. Close aiohttp session (fixes "Unclosed client session" warning)
    await nexnum_client.close()

    # 5. Save Playwright state + close Chrome
    await myntra_checker.shutdown()

    logger.info("✅ NexBot stopped cleanly.")


async def main() -> None:
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not set in .env — exiting.")
        sys.exit(1)

    me = await bot.get_me()
    logger.info("✅ Bot started: @%s", me.username)

    await set_commands()
    await checker.startup()   # starts cancel worker

    asyncio.create_task(myntra_checker.startup(), name="myntra_startup")
    logger.info("Playwright startup running in background...")

    # Restore SMS pollers for any active orders from the previous session
    from core.sms_poller import restore_pollers
    restored = await restore_pollers(bot)
    if restored:
        logger.info("Restored %d active SMS poller(s) from previous session", restored)

    logger.info("Polling started…")
    try:
        await bot.polling(none_stop=True, interval=0, timeout=20, skip_pending=True)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass   # suppress "^C" traceback — on_shutdown already ran inside main()
