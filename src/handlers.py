"""
Telegram message handlers for Lexi bot.
Includes onboarding, /settings, /quiz, /all, /filter, and all message routing.
"""

import logging
import re
from io import BytesIO
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.lexi import (
    detect_intent, explain_word, fix_spelling,
    compare_words, deduce_word, explain_quote, check_grammar,
)
from src.word_log import (
    log_word, get_review_state, get_settings, upsert_settings,
    get_week_words, get_all_words_paginated, get_words_in_range,
    set_onboard_state, get_onboard_state, end_onboarding,
    set_filter_state, get_filter_state, end_filter_state,
)
from src.review import handle_review_answer, start_review_for_user
from src.tts import generate_pronunciation, extract_word

logger = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SCOPE_LABELS = {"weekly": "This week", "monthly": "Last 30 days", "total": "All time"}


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _fmt_time(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


# ── Onboarding ────────────────────────────────────────────────────────────────

ONBOARD_STEPS = {
    0: {
        "text": (
            "Welcome to Lexi! 🎉\n\n"
            "I explain words, fix spelling, compare similar words, explain quotes, "
            "check your grammar, and quiz you weekly.\n\n"
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
    quiz = (
        f"✅ {DAY_NAMES[settings.get('quiz_day', 4)]} @ "
        f"{_fmt_time(settings.get('quiz_hour', 18), settings.get('quiz_minute', 0))}"
        if settings.get("quiz_enabled") else "❌"
    )
    lesson = (
        f"✅ {DAY_NAMES[settings.get('lesson_day', 4)]} @ "
        f"{_fmt_time(settings.get('lesson_hour', 18), settings.get('lesson_minute', 30))}"
        if settings.get("lesson_enabled") else "❌"
    )
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


# ── Commands ──────────────────────────────────────────────────────────────────

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
        "• Paste any quote to get it explained\n"
        "• Ask 'is this grammatically correct?' with your text\n\n"
        "During a quiz:\n"
        "• Type next to skip · Type previous to go back\n\n"
        "Commands:\n"
        "/start - Welcome\n"
        "/quiz - Start a quiz right now\n"
        "/mywords - Your words this week\n"
        "/all - All words you've ever looked up\n"
        "/filter - Filter words by date range\n"
        "/settings - Change your preferences\n"
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
        f"📖 <b>Your words this week:</b>\n\n{word_list}\n\nUse /quiz to test yourself on these now.",
        parse_mode="HTML"
    )


async def all_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _show_all_words(update.message, user_id, page=0)


async def _show_all_words(message, user_id: int, page: int):
    words, total = get_all_words_paginated(user_id, page=page, per_page=15)
    if not words:
        await message.reply_text("You haven't looked up any words yet. Send me a word to get started!")
        return
    total_pages = (total + 14) // 15
    word_list = "\n".join(f"• {w.capitalize()}" for w in words)
    text = (
        f"📚 <b>All your words</b> (page {page + 1} of {total_pages}, {total} total)\n\n"
        f"{word_list}"
    )
    buttons = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"allwords_{page - 1}"))
    if (page + 1) < total_pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"allwords_{page + 1}"))
    if row:
        buttons.append(row)
    await message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
    )


async def filter_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_filter_state(user_id, step="awaiting_start")
    await update.message.reply_text(
        "📅 <b>Filter words by date</b>\n\n"
        "Send me the <b>start date</b>:\n"
        "<code>YYYY-MM-DD</code>\n\n"
        "Example: <code>2026-04-01</code>\n\n"
        "Or type <b>cancel</b> to exit.",
        parse_mode="HTML"
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("Starting your quiz... ⏳")
    await start_review_for_user(user_id, context.bot, update.effective_chat.id)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_settings(update.effective_user.id, update.message)


async def _show_settings(user_id: int, message):
    settings = get_settings(user_id)
    wod = "ON 🟢" if settings.get("word_of_day") else "OFF 🔴"
    audio = "ON 🟢" if settings.get("audio") else "OFF 🔴"
    q_day = DAY_NAMES[settings.get("quiz_day", 4)]
    q_time = _fmt_time(settings.get("quiz_hour", 18), settings.get("quiz_minute", 0))
    quiz = f"ON 🟢 — {q_day} @ {q_time}" if settings.get("quiz_enabled") else "OFF 🔴"
    l_day = DAY_NAMES[settings.get("lesson_day", 4)]
    l_time = _fmt_time(settings.get("lesson_hour", 18), settings.get("lesson_minute", 30))
    lesson = f"ON 🟢 — {l_day} @ {l_time}" if settings.get("lesson_enabled") else "OFF 🔴"
    scope = SCOPE_LABELS.get(settings.get("quiz_scope", "weekly"), "This week")
    week_start = DAY_NAMES[settings.get("week_start", 0)]
    keyboard = [
        [InlineKeyboardButton(f"🌟 Word of the Day: {wod}", callback_data="set_toggle_wod")],
        [InlineKeyboardButton(f"🔊 Audio: {audio}", callback_data="set_toggle_audio")],
        [InlineKeyboardButton(f"🧠 Quiz: {quiz}", callback_data="set_toggle_quiz")],
        [InlineKeyboardButton("📅 Quiz day", callback_data="set_qday"),
         InlineKeyboardButton("⏰ Quiz time", callback_data="set_qtime")],
        [InlineKeyboardButton(f"📚 Lesson: {lesson}", callback_data="set_toggle_lesson")],
        [InlineKeyboardButton("📅 Lesson day", callback_data="set_lday"),
         InlineKeyboardButton("⏰ Lesson time", callback_data="set_ltime")],
        [InlineKeyboardButton(f"📊 Quiz scope: {scope}", callback_data="set_scope")],
        [InlineKeyboardButton(f"📆 Week starts: {week_start}", callback_data="set_weekstart")],
    ]
    await message.reply_text(
        "⚙️ <b>Your Lexi Settings</b>\n\nTap anything to change it.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _refresh_settings(query, user_id: int):
    settings = get_settings(user_id)
    wod = "ON 🟢" if settings.get("word_of_day") else "OFF 🔴"
    audio = "ON 🟢" if settings.get("audio") else "OFF 🔴"
    q_day = DAY_NAMES[settings.get("quiz_day", 4)]
    q_time = _fmt_time(settings.get("quiz_hour", 18), settings.get("quiz_minute", 0))
    quiz = f"ON 🟢 — {q_day} @ {q_time}" if settings.get("quiz_enabled") else "OFF 🔴"
    l_day = DAY_NAMES[settings.get("lesson_day", 4)]
    l_time = _fmt_time(settings.get("lesson_hour", 18), settings.get("lesson_minute", 30))
    lesson = f"ON 🟢 — {l_day} @ {l_time}" if settings.get("lesson_enabled") else "OFF 🔴"
    scope = SCOPE_LABELS.get(settings.get("quiz_scope", "weekly"), "This week")
    week_start = DAY_NAMES[settings.get("week_start", 0)]
    keyboard = [
        [InlineKeyboardButton(f"🌟 Word of the Day: {wod}", callback_data="set_toggle_wod")],
        [InlineKeyboardButton(f"🔊 Audio: {audio}", callback_data="set_toggle_audio")],
        [InlineKeyboardButton(f"🧠 Quiz: {quiz}", callback_data="set_toggle_quiz")],
        [InlineKeyboardButton("📅 Quiz day", callback_data="set_qday"),
         InlineKeyboardButton("⏰ Quiz time", callback_data="set_qtime")],
        [InlineKeyboardButton(f"📚 Lesson: {lesson}", callback_data="set_toggle_lesson")],
        [InlineKeyboardButton("📅 Lesson day", callback_data="set_lday"),
         InlineKeyboardButton("⏰ Lesson time", callback_data="set_ltime")],
        [InlineKeyboardButton(f"📊 Quiz scope: {scope}", callback_data="set_scope")],
        [InlineKeyboardButton(f"📆 Week starts: {week_start}", callback_data="set_weekstart")],
    ]
    await query.edit_message_text(
        "⚙️ <b>Your Lexi Settings</b>\n\nTap anything to change it.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def _day_picker(prefix: str) -> list:
    return [
        [InlineKeyboardButton(d, callback_data=f"{prefix}_{i}") for i, d in enumerate(DAY_SHORT[:4])],
        [InlineKeyboardButton(d, callback_data=f"{prefix}_{i+4}") for i, d in enumerate(DAY_SHORT[4:])]
    ]


def _time_picker(prefix: str) -> list:
    rows = []
    row = []
    for h in range(6, 24):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"{prefix}_{h}_0"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


# ── Callback handler ──────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("allwords_"):
        page = int(data.split("_")[1])
        await query.message.delete()
        await _show_all_words(query.message, user_id, page)
        return

    if data.startswith("ob_"):
        onboard = get_onboard_state(user_id)
        if not onboard:
            return
        await query.edit_message_reply_markup(reply_markup=None)
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
        return

    if data.startswith("set_"):
        if data == "set_toggle_wod":
            upsert_settings(user_id, word_of_day=0 if get_settings(user_id).get("word_of_day") else 1)
            await _refresh_settings(query, user_id)
        elif data == "set_toggle_audio":
            upsert_settings(user_id, audio=0 if get_settings(user_id).get("audio") else 1)
            await _refresh_settings(query, user_id)
        elif data == "set_toggle_quiz":
            upsert_settings(user_id, quiz_enabled=0 if get_settings(user_id).get("quiz_enabled") else 1)
            await _refresh_settings(query, user_id)
        elif data == "set_toggle_lesson":
            upsert_settings(user_id, lesson_enabled=0 if get_settings(user_id).get("lesson_enabled") else 1)
            await _refresh_settings(query, user_id)
        elif data == "set_qday":
            await query.edit_message_text("📅 Which day for your quiz?",
                reply_markup=InlineKeyboardMarkup(_day_picker("set_qday")))
        elif data.startswith("set_qday_") and len(data) > len("set_qday_"):
            upsert_settings(user_id, quiz_day=int(data.split("_")[-1]))
            await _refresh_settings(query, user_id)
        elif data == "set_lday":
            await query.edit_message_text("📅 Which day for your lesson?",
                reply_markup=InlineKeyboardMarkup(_day_picker("set_lday")))
        elif data.startswith("set_lday_") and len(data) > len("set_lday_"):
            upsert_settings(user_id, lesson_day=int(data.split("_")[-1]))
            await _refresh_settings(query, user_id)
        elif data == "set_qtime":
            await query.edit_message_text("⏰ What time for your quiz? (Lagos time)",
                reply_markup=InlineKeyboardMarkup(_time_picker("set_qtime")))
        elif data.startswith("set_qtime_") and data != "set_qtime":
            parts = data.split("_")
            upsert_settings(user_id, quiz_hour=int(parts[-2]), quiz_minute=int(parts[-1]))
            await _refresh_settings(query, user_id)
        elif data == "set_ltime":
            await query.edit_message_text("⏰ What time for your lesson? (Lagos time)",
                reply_markup=InlineKeyboardMarkup(_time_picker("set_ltime")))
        elif data.startswith("set_ltime_") and data != "set_ltime":
            parts = data.split("_")
            upsert_settings(user_id, lesson_hour=int(parts[-2]), lesson_minute=int(parts[-1]))
            await _refresh_settings(query, user_id)
        elif data == "set_scope":
            keyboard = [
                [InlineKeyboardButton("📅 This week", callback_data="set_scope_weekly")],
                [InlineKeyboardButton("📆 Last 30 days", callback_data="set_scope_monthly")],
                [InlineKeyboardButton("📚 All time", callback_data="set_scope_total")],
            ]
            await query.edit_message_text(
                "📊 <b>Quiz scope</b>\n\nWhich words should be included in your quiz?",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data.startswith("set_scope_"):
            upsert_settings(user_id, quiz_scope=data.replace("set_scope_", ""))
            await _refresh_settings(query, user_id)
        elif data == "set_weekstart":
            keyboard = [
                [InlineKeyboardButton("Monday (default)", callback_data="set_weekstart_0"),
                 InlineKeyboardButton("Sunday", callback_data="set_weekstart_6")]
            ]
            await query.edit_message_text("📆 Which day should your week start?",
                reply_markup=InlineKeyboardMarkup(keyboard))
        elif data.startswith("set_weekstart_"):
            upsert_settings(user_id, week_start=int(data.split("_")[-1]))
            await _refresh_settings(query, user_id)


# ── Message handler ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return

    if get_onboard_state(user_id):
        await update.message.reply_text("Please complete the setup first — tap one of the buttons above. 👆")
        return

    filter_state = get_filter_state(user_id)
    if filter_state:
        await _handle_filter_flow(update, user_id, text, filter_state)
        return

    state = get_review_state(user_id)
    if state:
        handled = await handle_review_answer(user_id, context.bot, update.effective_chat.id, text)
        if handled:
            return

    await update.message.reply_text("On it... ⏳")

    try:
        intent = detect_intent(text)
        settings = get_settings(user_id)

        if intent == "SPELLING":
            await _send_llm_response(update.message, fix_spelling(text))
        elif intent == "COMPARE":
            await _send_llm_response(update.message, compare_words(text))
        elif intent == "QUOTE_EXPLANATION":
            await _send_llm_response(update.message, explain_quote(text))
        elif intent == "GRAMMAR_CHECK":
            await _send_llm_response(update.message, check_grammar(text))
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
        await update.message.reply_text("Hmm, something went wrong on my end. Try again in a moment. 🙏")


async def _handle_filter_flow(update: Update, user_id: int, text: str, state: dict):
    if text.lower() == "cancel":
        end_filter_state(user_id)
        await update.message.reply_text("Filter cancelled.")
        return
    step = state["step"]
    if step == "awaiting_start":
        try:
            datetime.strptime(text, "%Y-%m-%d")
            set_filter_state(user_id, step="awaiting_end", start_date=text)
            await update.message.reply_text(
                f"Got it — starting from <b>{text}</b>.\n\n"
                "Now send the <b>end date</b>:\n<code>YYYY-MM-DD</code>\n\nOr type <b>cancel</b>.",
                parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text(
                "Use this format: <code>YYYY-MM-DD</code>\nExample: <code>2026-04-01</code>",
                parse_mode="HTML"
            )
    elif step == "awaiting_end":
        try:
            datetime.strptime(text, "%Y-%m-%d")
            start = state["start_date"]
            words = get_words_in_range(user_id, start + "T00:00:00", text + "T23:59:59")
            end_filter_state(user_id)
            if not words:
                await update.message.reply_text(f"No words found between {start} and {text}.")
                return
            word_list = "\n".join(f"• {w.capitalize()}" for w in words)
            await update.message.reply_text(
                f"📅 <b>Words from {start} to {text}</b> ({len(words)} words)\n\n{word_list}",
                parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text(
                "Use this format: <code>YYYY-MM-DD</code>", parse_mode="HTML"
            )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")