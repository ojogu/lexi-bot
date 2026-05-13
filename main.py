"""
Lexi bot entry point.
"""

import logging
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from src.config import TELEGRAM_TOKEN
from src.handlers import (
    start, help_command, my_words, all_words, filter_words,
    quiz_command, settings_command,
    handle_message, handle_callback, error_handler,
)
from src.scheduler import build_scheduler
from src.word_log import init_db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start",    "Welcome / re-run onboarding"),
    BotCommand("quiz",     "Start a quiz right now"),
    BotCommand("mywords",  "Your words this week"),
    BotCommand("all",      "All words you've ever looked up"),
    BotCommand("filter",   "Filter words by date range"),
    BotCommand("settings", "Change your preferences"),
    BotCommand("help",     "How to use Lexi"),
]


async def on_startup(app):
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered with Telegram")


def main():
    init_db()
    logger.info("Database initialised")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("mywords", my_words))
    app.add_handler(CommandHandler("all", all_words))
    app.add_handler(CommandHandler("filter", filter_words))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    scheduler = build_scheduler(app.bot)
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Lexi bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()