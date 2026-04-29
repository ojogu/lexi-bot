"""
Lexi bot entry point.
"""

import logging
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from config import TELEGRAM_TOKEN
from handlers import start, help_command, my_words, handle_message, error_handler
from scheduler import build_scheduler
from word_log import init_db

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start",   "Welcome message"),
    BotCommand("help",    "How to use Lexi"),
    BotCommand("mywords", "See your words for this week"),
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

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("mywords", my_words))

    # All text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

    # Scheduler (Friday review)
    scheduler = build_scheduler(app.bot)
    scheduler.start()
    logger.info("Scheduler started")

    logger.info("Lexi bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
