"""
Telegram message handlers for Lexi bot.
Includes onboarding, /settings, and all message routing.
"""

import logging
import re
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.lexi import (
    detect_intent, explain_word, fix_spelling,
    compare_words, deduce_word, explain_quote,
)
from src.word_log import (
    log_word, get_review_state, get_settings, upsert_settings,
    get_week_words, set_onboard_state, get_onboard_state, end_onboarding,
)
from src.review import handle_review_answer
from src.tts import generate_pronunciation, extract_word

logger = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def _send_llm_response(message, text: str):
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


ONBOARD_STEPS = {
    0: {
        "text": (
            "Welcome to Lexi! 🎉\n\n"
            "I explain words, fix spelling, compare similar words, explain quotes, "
            "and quiz you weekly.\n\n"
            "Do you want a <b>Word of the Day</b> every morning at 8 AM?"
        ),
        "buttons": [
            [InlineKeyboardButton("✅ Yes please", callback_data="ob_wod_1"),
             InlineKeyboardButton("❌ No thanks", callback_data="ob_wod_0")]
        ]
    },
    1: {
        "text": "Do you want <b>audio pronunciation</b> after every word lookup?",
        "buttons": [
            [InlineKeyboardButton("✅ Yes", callback_data="ob_audio_1"),
             InlineKeyboardButton("❌ No", callback_data="ob_audio_0")]
        ]
    },
    2: {
        "text": "Do you want a <b>weekly review quiz</b> on the words you looked up?",
        "buttons": [
            [InlineKeyboardButton("✅ Yes", callback_data="ob_quiz_1"),
             InlineKeyboardButton("❌ No", callback_data="ob_quiz_0")]
        ]
    },
    3: {
        "text": "Which day do you want your <b>quiz</b>?",
        "buttons": [
            [InlineKeyboardButton(d, callback_data=f"ob_qday_{i}") for i, d in enumerate(DAY_SHORT[:4])],
            [InlineKeyboardButton(d, callback_data=f"ob_qday_{i+4}") for i, d in enumerate(DAY_SHORT[4:])]
        ]
    },
    4: {
        "text": "Do you want a weekly <b>English lesson</b>?",
        "buttons": [
            [InlineKeyboardButton("✅ Yes", callback_data="ob_lesson_1"),
             InlineKeyboardButton("❌ No", callback_data="ob_lesson_0")]
        ]
    },
    5: {
        "text": "Which day do you want your <b>lesson</b>?",
        "buttons": [
            [InlineKeyboardButton(d, callback_data=f"ob_lday_{i}") for i, d in enumerate(DAY_SHORT[:4])],
            [InlineKeyboardButton(d, callback_data=f"ob_lday_{i+4}") for i, d in enumerate(DAY_SHORT[4:])]
        ]
    },
}


async def _send_onboard_step(chat_id: int, step: int, bot):
    if step not in ONBOARD_STEPS:
        return
    data = ONBOARD_STEPS[step]
    await bot.send_message(
        chat_id=chat_id,
        text=data["text"],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(data["buttons"])
    )


async def _finish_onboarding(user_id: int, bot, chat_id: int):
    end_onboarding(user_id)
    settings = get_settings(user_id)
    wod = "✅" if settings.get("word_of_day") else "❌"
    audio = "✅" if settings.get("audio") else "❌"
    quiz = f"✅ {DAY_NAMES[settings.get('quiz_day', 4)]}" if settings.get("quiz_enabled") else "❌"
    lesson = f"✅ {DAY_NAMES[settings.get('lesson_day', 4)]}" if settings.get("lesson_enabled") else "❌"
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🎉 <b>You're all set!</b>\n\n"
            f"🌟 Word of the Day: {wod}\n"
            f"🔊 Audio Pronunciation: {audio}\n"
            f"🧠 Weekly Quiz: {quiz}\n"
            f"📚 Weekly Lesson: {lesson}\n\n"
            "Change anything anytime with /settings\n\n"
            "Now send me any English word to get started 👇"
        ),
        parse_mode="HTML"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name or "there"
    settings = get_settings(user_id)
    if settings.get("onboarded"):
        await update.message.reply_text(
            f"Hey {name}! Send me any word, or use /help to see everything I can do."
        )
        return
    set_onboard_state(user_id, step=0, active=1)
    await update.message.reply_text(
        f"👋 Hey {name}! I'm <b>Lexi</b>, your personal vocab tutor.",
        parse_mode="HTML"
    )
    await _send_onboard_step(update.effective_chat.id, 0, context.bot)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How to use Lexi:\n\n"
        "• Send any word to look it up\n"
        "• Send a misspelled word to fix it\n"
        "• Ask 'difference between too and to'\n"
        "• Ask 'what's the word for someone who hates people'\n"
        "• Paste any quote to get it explained\n\n"
        "During a quiz:\n"
        "• Type next to skip a question\n"
        "• Type previous to go back\n\n"
        "Commands:\n"
        "/start - Welcome\n"
        "/settings - Change your preferences\n"
        "/mywords - See your words this week\n"
        "/help - This message"
    )


async def my_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"I'll quiz you on these on your scheduled day."
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_settings(update.effective_user.id, update.message)


async def _show_settings(user_id: int, message):
    settings = get_settings(user_id)
    wod = "ON 🟢" if settings.get("word_of_day") else "OFF 🔴"
    audio = "ON 🟢" if settings.get("audio") else "OFF 🔴"
    quiz = f"ON 🟢 — {DAY_NAMES[settings.get('quiz_day', 4)]}" if settings.get("quiz_enabled") else "OFF 🔴"
    lesson = f"ON 🟢 — {DAY_NAMES[settings.get('lesson_day', 4)]}" if settings.get("lesson_enabled") else "OFF 🔴"
    keyboard = [
        [InlineKeyboardButton(f"🌟 Word of the Day: {wod}", callback_data="set_toggle_wod")],
        [InlineKeyboardButton(f"🔊 Audio: {audio}", callback_data="set_toggle_audio")],
        [InlineKeyboardButton(f"🧠 Quiz: {quiz}", callback_data="set_toggle_quiz")],
        [InlineKeyboardButton(f"📚 Lesson: {lesson}", callback_data="set_toggle_lesson")],
        [InlineKeyboardButton("📅 Change quiz day", callback_data="set_qday"),
         InlineKeyboardButton("📅 Change lesson day", callback_data="set_lday")],
    ]
    await message.reply_text(
        "⚙️ <b>Your Lexi Settings</b>\n\nTap anything to change it.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("ob_"):
        onboard = get_onboard_state(user_id)
        if not onboard:
            return

        if data.startswith("ob_wod_"):
            upsert_settings(user_id, word_of_day=int(data[-1]))
            set_onboard_state(user_id, step=1)
            await _send_onboard_step(chat_id, 1, context.bot)
        elif data.startswith("ob_audio_"):
            upsert_settings(user_id, audio=int(data[-1]))
            set_onboard_state(user_id, step=2)
            await _send_onboard_step(chat_id, 2, context.bot)
        elif data.startswith("ob_quiz_"):
            val = int(data[-1])
            upsert_settings(user_id, quiz_enabled=val)
            next_step = 3 if val else 4
            set_onboard_state(user_id, step=next_step)
            await _send_onboard_step(chat_id, next_step, context.bot)
        elif data.startswith("ob_qday_"):
            upsert_settings(user_id, quiz_day=int(data.split("_")[-1]))
            set_onboard_state(user_id, step=4)
            await _send_onboard_step(chat_id, 4, context.bot)
        elif data.startswith("ob_lesson_"):
            val = int(data[-1])
            upsert_settings(user_id, lesson_enabled=val)
            if val:
                set_onboard_state(user_id, step=5)
                await _send_onboard_step(chat_id, 5, context.bot)
            else:
                await _finish_onboarding(user_id, context.bot, chat_id)
        elif data.startswith("ob_lday_"):
            upsert_settings(user_id, lesson_day=int(data.split("_")[-1]))
            await _finish_onboarding(user_id, context.bot, chat_id)

    elif data.startswith("set_"):
        settings = get_settings(user_id)

        if data == "set_toggle_wod":
            upsert_settings(user_id, word_of_day=0 if settings.get("word_of_day") else 1)
        elif data == "set_toggle_audio":
            upsert_settings(user_id, audio=0 if settings.get("audio") else 1)
        elif data == "set_toggle_quiz":
            upsert_settings(user_id, quiz_enabled=0 if settings.get("quiz_enabled") else 1)
        elif data == "set_toggle_lesson":
            upsert_settings(user_id, lesson_enabled=0 if settings.get("lesson_enabled") else 1)
        elif data == "set_qday":
            keyboard = [
                [InlineKeyboardButton(d, callback_data=f"set_qday_{i}") for i, d in enumerate(DAY_SHORT[:4])],
                [InlineKeyboardButton(d, callback_data=f"set_qday_{i+4}") for i, d in enumerate(DAY_SHORT[4:])]
            ]
            await query.message.reply_text("Which day for your quiz?", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        elif data == "set_lday":
            keyboard = [
                [InlineKeyboardButton(d, callback_data=f"set_lday_{i}") for i, d in enumerate(DAY_SHORT[:4])],
                [InlineKeyboardButton(d, callback_data=f"set_lday_{i+4}") for i, d in enumerate(DAY_SHORT[4:])]
            ]
            await query.message.reply_text("Which day for your lesson?", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        elif data.startswith("set_qday_"):
            upsert_settings(user_id, quiz_day=int(data.split("_")[-1]))
        elif data.startswith("set_lday_"):
            upsert_settings(user_id, lesson_day=int(data.split("_")[-1]))

        settings = get_settings(user_id)
        wod = "ON 🟢" if settings.get("word_of_day") else "OFF 🔴"
        audio = "ON 🟢" if settings.get("audio") else "OFF 🔴"
        quiz = f"ON 🟢 — {DAY_NAMES[settings.get('quiz_day', 4)]}" if settings.get("quiz_enabled") else "OFF 🔴"
        lesson = f"ON 🟢 — {DAY_NAMES[settings.get('lesson_day', 4)]}" if settings.get("lesson_enabled") else "OFF 🔴"
        keyboard = [
            [InlineKeyboardButton(f"🌟 Word of the Day: {wod}", callback_data="set_toggle_wod")],
            [InlineKeyboardButton(f"🔊 Audio: {audio}", callback_data="set_toggle_audio")],
            [InlineKeyboardButton(f"🧠 Quiz: {quiz}", callback_data="set_toggle_quiz")],
            [InlineKeyboardButton(f"📚 Lesson: {lesson}", callback_data="set_toggle_lesson")],
            [InlineKeyboardButton("📅 Change quiz day", callback_data="set_qday"),
             InlineKeyboardButton("📅 Change lesson day", callback_data="set_lday")],
        ]
        await query.edit_message_text(
            "⚙️ <b>Your Lexi Settings</b>\n\nTap anything to change it.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        return

    if get_onboard_state(user_id):
        await update.message.reply_text(
            "Please complete the setup first — tap one of the buttons above. 👆"
        )
        return

    state = get_review_state(user_id)
    if state:
        handled = await handle_review_answer(
            user_id, context.bot, update.effective_chat.id, text
        )
        if handled:
            return

    await update.message.reply_text("On it... ⏳")

    try:
        intent = detect_intent(text)
        settings = get_settings(user_id)

        if intent == "SPELLING":
            result = fix_spelling(text)
            await _send_llm_response(update.message, result)

        elif intent == "COMPARE":
            result = compare_words(text)
            await _send_llm_response(update.message, result)

        elif intent == "QUOTE_EXPLANATION":
            result = explain_quote(text)
            await _send_llm_response(update.message, result)

        elif intent == "WORD_DEDUCTION":
            word, result = deduce_word(text)
            await _send_llm_response(update.message, result)
            if word:
                log_word(user_id, word)
                if settings.get("audio", 1):
                    await _send_pronunciation(update.message, word)

        else:  # WORD_LOOKUP
            result = explain_word(text)
            clean = extract_word(text)
            log_word(user_id, clean)
            await _send_llm_response(update.message, result)
            if settings.get("audio", 1):
                await _send_pronunciation(update.message, text)

    except Exception as e:
        logger.error(f"Error handling message '{text}': {e}")
        await update.message.reply_text(
            "Hmm, something went wrong on my end. Try again in a moment. 🙏"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")