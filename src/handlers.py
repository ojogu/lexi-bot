"""
Telegram message handlers for Lexi bot.
"""

import logging
import re
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes

from src.lexi import detect_intent, explain_word, fix_spelling, compare_words
from src.word_log import log_word, get_review_state
from src.review import handle_review_answer
from src.tts import generate_pronunciation, extract_word

logger = logging.getLogger(__name__)


async def _send_llm_response(message, text: str):
    """
    Send LLM-generated HTML text safely.
    Falls back to plain text if Telegram rejects the HTML.
    """
    try:
        await message.reply_text(text, parse_mode="HTML")
    except Exception:
        try:
            plain = re.sub(r'<[^>]+>', '', text)
            await message.reply_text(plain)
        except Exception as e:
            logger.error(f"Failed to send response: {e}")
            await message.reply_text("Got the answer but had trouble formatting it. Try again. 🙏")


async def _send_pronunciation(message, word: str):
    """
    Generate and send a voice note for the word.
    Sends a status message first since TTS generation can take a few seconds.
    Fails silently — the text card already delivered value.
    """
    try:
        status = await message.reply_text("🎙️ Generating pronunciation...")
        audio_bytes = generate_pronunciation(word)
        await status.delete()
        if audio_bytes:
            await message.reply_voice(
                voice=BytesIO(audio_bytes),
                caption=f"🔊 {extract_word(word).capitalize()}",
            )
    except Exception as e:
        logger.error(f"Failed to send pronunciation for '{word}': {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey {name}! I'm Lexi, your personal vocab tutor.\n\n"
        f"Here's what I can do:\n"
        f"• Look up any word - meaning, pronunciation, examples, memory hook\n"
        f"• Fix your spelling - just send the word or ask 'how do you spell...'\n"
        f"• Compare words - 'difference between too and to', 'affect vs effect'\n\n"
        f"Every Friday at 6 PM, I'll quiz you on the words you looked up that week.\n\n"
        f"Try it now. Send me anything 👇"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How to use Lexi:\n\n"
        "Look up a word: just send it\n"
        "Example: volatile\n\n"
        "Fix spelling: send the word or ask directly\n"
        "Example: emmbarasment  or  how do you spell necessary\n\n"
        "Compare words: ask the difference\n"
        "Example: difference between too and to  or  affect vs effect\n\n"
        "Every Friday evening I'll quiz you on your week's words.\n"
        "Answer my questions and I'll tell you if you're right.\n\n"
        "Commands:\n"
        "/start - Welcome message\n"
        "/help - This message\n"
        "/mywords - See words you looked up this week"
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
        f"📖 Your words this week:\n\n{word_list}\n\n"
        f"I'll quiz you on these Friday at 6 PM."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    state = get_review_state(user_id)
    if state:
        handled = await handle_review_answer(
            user_id, context.bot, update.effective_chat.id, text
        )
        if handled:
            return

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
            await _send_llm_response(update.message, result)

        elif intent == "COMPARE":
            result = compare_words(text)
            await _send_llm_response(update.message, result)

        else:  # WORD_LOOKUP
            result = explain_word(text)
            log_word(user_id, text)
            await _send_llm_response(update.message, result)
            await _send_pronunciation(update.message, text)

    except Exception as e:
        logger.error(f"Error handling message '{text}': {e}")
        await update.message.reply_text(
            "Hmm, something went wrong on my end. Try again in a moment. 🙏"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")