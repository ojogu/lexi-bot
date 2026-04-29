"""
Telegram message handlers for Lexi bot.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from lexi import detect_intent, explain_word, fix_spelling, compare_words
from word_log import log_word, get_review_state
from review import handle_review_answer

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey {name}! I'm *Lexi*, your personal vocab tutor.\n\n"
        f"Here's what I can do:\n"
        f"• *Look up any word* — meaning, pronunciation, examples, memory hook\n"
        f"• *Fix your spelling* — just send the word or ask 'how do you spell...'\n"
        f"• *Compare words* — 'difference between too and to', 'affect vs effect'\n\n"
        f"Every Friday at 6 PM, I'll quiz you on the words you looked up that week.\n\n"
        f"Try it now. Send me anything 👇",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*How to use Lexi:*\n\n"
        "*Look up a word:* just send it\n"
        "Example: `volatile`\n\n"
        "*Fix spelling:* send the word or ask directly\n"
        "Example: `emmbarasment` or `how do you spell necessary`\n\n"
        "*Compare words:* ask the difference\n"
        "Example: `difference between too and to` or `affect vs effect`\n\n"
        "Every Friday evening I'll quiz you on your week's words.\n"
        "Answer my questions and I'll tell you if you're right.\n\n"
        "*Commands:*\n"
        "/start - Welcome message\n"
        "/help - This message\n"
        "/mywords - See words you looked up this week",
        parse_mode="Markdown"
    )


async def my_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from word_log import get_week_words
    user_id = update.effective_user.id
    words = get_week_words(user_id)
    if not words:
        await update.message.reply_text(
            "You haven't looked up any words this week yet. Send me a word to get started!"
        )
        return
    word_list = "\n".join(f"• {w.capitalize()}" for w in words)
    await update.message.reply_text(
        f"📖 *Your words this week:*\n\n{word_list}\n\n"
        f"I'll quiz you on these Friday at 6 PM.",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    # If review is active, route to review handler first
    state = get_review_state(user_id)
    if state:
        handled = await handle_review_answer(
            user_id, context.bot, update.effective_chat.id, text
        )
        if handled:
            return

    # Detect intent then route accordingly
    # Hard cap: if input is very long it's not a vocab query
    if len(text.split()) > 12:
        await update.message.reply_text(
            "Keep it short. Send me a word, a spelling question, or something like "
            "'difference between too and to'. 🙂"
        )
        return

    await update.message.reply_text("On it... ⏳")

    try:
        intent = detect_intent(text)

        if intent == "SPELLING":
            result = fix_spelling(text)
            # Spelling corrections don't get logged as word lookups
            await update.message.reply_text(result, parse_mode="Markdown")

        elif intent == "COMPARE":
            result = compare_words(text)
            # Log both words if we can parse them, else skip logging
            await update.message.reply_text(result, parse_mode="Markdown")

        else:  # WORD_LOOKUP (default)
            result = explain_word(text)
            log_word(user_id, text)
            await update.message.reply_text(result, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling message '{text}': {e}")
        await update.message.reply_text(
            "Hmm, something went wrong on my end. Try again in a moment. 🙏"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
