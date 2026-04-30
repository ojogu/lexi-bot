"""
Telegram message handlers for Lexi bot.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.lexi import detect_intent, explain_word, fix_spelling, compare_words
from src.word_log import log_word, get_review_state
from src.review import handle_review_answer

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey {name}! I'm <b>Lexi</b>, your personal vocab tutor.\n\n"
        f"Here's what I can do:\n"
        f"• <b>Look up any word</b> — meaning, pronunciation, examples, memory hook\n"
        f"• <b>Fix your spelling</b> — just send the word or ask 'how do you spell...'\n"
        f"• <b>Compare words</b> — 'difference between too and to', 'affect vs effect'\n\n"
        f"Every Friday at 6 PM, I'll quiz you on the words you looked up this week.\n\n"
        f"Try it now. Send me anything 👇",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>How to use Lexi:</b>\n\n"
        "<b>Look up a word:</b> just send it\n"
        "Example: <code>volatile</code>\n\n"
        "<b>Fix spelling:</b> send the word or ask directly\n"
        "Example: <code>emmbarasment</code> or <code>how do you spell necessary</code>\n\n"
        "<b>Compare words:</b> ask the difference\n"
        "Example: <code>difference between too and to</code> or <code>affect vs effect</code>\n\n"
        "Every Friday evening I'll quiz you on your week's words.\n"
        "Answer my questions and I'll tell you if you're right.\n\n"
        "<b>Commands:</b>\n"
        "/start - Welcome message\n"
        "/help - This message\n"
        "/mywords - See words you looked up this week",
        parse_mode="HTML",
    )


async def my_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from src.word_log import get_week_words

    user_id = update.effective_user.id
    words = get_week_words(user_id)
    if not words:
        await update.message.reply_text(
            "You haven't looked up any words this week yet. Send me a word to get started!"
        )
        return
    word_list = "\n".join(f"• {w.capitalize()}" for w in words)
    await update.message.reply_text(
        f"📖 <b>Your words this week:</b>\n\n{word_list}\n\n"
        f"I'll quiz you on these Friday at 6 PM.",
        parse_mode="HTML",
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
            await update.message.reply_text(result, parse_mode="HTML")

        elif intent == "COMPARE":
            result = compare_words(text)
            # Log both words if we can parse them, else skip logging
            await update.message.reply_text(result, parse_mode="HTML")

        else:  # WORD_LOOKUP (default)
            result = explain_word(text)
            log_word(user_id, text)
            await update.message.reply_text(result, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error handling message '{text}': {e}")
        await update.message.reply_text(
            "Hmm, something went wrong on my end. Try again in a moment. 🙏"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
