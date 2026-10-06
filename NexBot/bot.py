"""NexBot — Entry point.

To add a new platform: just add a PlatformDef to utils/platforms.py.
bot.py loops over PLATFORMS automatically — zero manual wiring needed.

Run:  python bot.py
"""
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NEXCHECKER_ROOT = ROOT.parent   # D:/Nex-Projects/NexChecker  (for bigbasket_check.py, etc.)
for p in (str(ROOT), str(NEXCHECKER_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand

from utils.config import BOT_TOKEN
from core.nexnum_api import nexnum_client
from handlers.start import StartHandler
from handlers.checker import CheckerHandler
from handlers.callbacks import CallbackHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NexBot")

# ── Bot instance ──────────────────────────────────────────────────────────────
bot = AsyncTeleBot(BOT_TOKEN, parse_mode="HTML")

# ── Platform registry + one CheckerHandler per platform ──────────────────────
from utils.platforms import get_platforms
PLATFORMS = get_platforms()

checkers: dict[str, CheckerHandler] = {
    key: CheckerHandler(bot, platform)
    for key, platform in PLATFORMS.items()
}

# ── Handler instances ─────────────────────────────────────────────────────────
start_hdlr = StartHandler(bot)
cb_hdlr    = CallbackHandler(bot, checkers, start_hdlr=start_hdlr)

# ─────────────────────────────────────────────────────────────────────────────
# Command handlers — one per platform + shared commands
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
async def cmd_start(msg):
    await start_hdlr.handle_start(msg)

@bot.message_handler(commands=["mystats"])
async def cmd_stats(msg):
    await start_hdlr.handle_mystats(msg)

@bot.message_handler(commands=["help"])
async def cmd_help(msg):
    await start_hdlr.handle_help(msg)

# Dynamically register /<platform> commands from the registry
def _make_platform_handler(checker: CheckerHandler):
    async def _handler(msg):
        await checker.handle_command(msg)
    return _handler

for _key, _checker in checkers.items():
    bot.message_handler(commands=[_checker.platform.command])(
        _make_platform_handler(_checker)
    )


# ── Intercept API key input (any plain text while waiting for key) ─────────────
@bot.message_handler(func=lambda m: m.content_type == "text" and not m.text.startswith("/"))
async def catch_text(msg):
    await start_hdlr.handle_text_message(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Callback dispatcher — handles both nex: (new) and myntra_ (legacy)
# ─────────────────────────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: (
    c.data.startswith("nex:") or
    c.data.startswith("myntra_") or
    c.data.startswith("sms_copy_")
))
async def cb_dispatch(call):
    await cb_hdlr.dispatch(call)


# ─────────────────────────────────────────────────────────────────────────────
# Startup / shutdown
# ─────────────────────────────────────────────────────────────────────────────

async def set_commands() -> None:
    """Register all platform commands + shared commands with Telegram."""
    commands = [
        BotCommand("start",   "Start the bot / main menu"),
        BotCommand("mystats", "View your check statistics"),
        BotCommand("help",    "Show help & usage"),
    ]
    for platform in PLATFORMS.values():
        commands.append(BotCommand(platform.command, platform.description))
    await bot.set_my_commands(commands)


async def on_shutdown() -> None:
    """Graceful shutdown — cancel tasks, close sessions, save state."""
    logger.info("⏹  Shutting down NexBot…")

    # 1. Stop Telegram polling
    try:
        await bot.close_session()
    except Exception:
        pass

    # 2. Cancel all active checker session tasks (across ALL platforms)
    total_tasks = 0
    for key, checker in checkers.items():
        for uid, task in list(checker.session_tasks.items()):
            if task and not task.done():
                task.cancel()
                total_tasks += 1
        if checker.session_tasks:
            await asyncio.gather(*checker.session_tasks.values(), return_exceptions=True)
        checker.active_sessions.clear()
        checker.session_tasks.clear()
    if total_tasks:
        logger.info("Cancelled %d active session task(s)", total_tasks)

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

    # 4. Close aiohttp session
    await nexnum_client.close()

    # 5. Shutdown all platform checkers (save Playwright state, close Chrome, etc.)
    for key, platform in PLATFORMS.items():
        try:
            await platform.checker.shutdown()
        except Exception as exc:
            logger.warning("Shutdown error for %s: %s", key, exc)

    logger.info("✅ NexBot stopped cleanly.")


async def main() -> None:
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not set in .env — exiting.")
        sys.exit(1)

    me = await bot.get_me()
    logger.info("✅ Bot started: @%s", me.username)

    await set_commands()

    # Start cancel worker (shared across all platforms — only one needed)
    await next(iter(checkers.values())).startup()

    # Start all platform checkers that need warmup (e.g. Myntra Chrome context)
    # Non-warmup platforms (BigBasket) just do a state file check
    for key, platform in PLATFORMS.items():
        if platform.needs_warmup:
            asyncio.create_task(platform.checker.startup(), name=f"{key}_startup")
            logger.info("Playwright startup running in background... (%s)", key)
        else:
            asyncio.create_task(platform.checker.startup(), name=f"{key}_startup")

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
