"""
Review session logic.
Handles quiz questions, answer grading, navigation (next/previous), and lesson delivery.
"""

import re
import json
import sqlite3
import logging
from src.lexi import generate_review_question, grade_sentence, grade_answer, generate_lesson
from src.word_log import (
    get_week_words, set_review_state, get_review_state,
    advance_review, end_review, get_settings,
)
from src.config import DB_PATH

logger = logging.getLogger(__name__)

NAV_NEXT = {"next", "skip"}
NAV_PREV = {"previous", "prev", "back"}

FILL_HINT = "Send <b>A</b>, <b>B</b>, <b>C</b> or <b>D</b> — or type <b>next</b> to skip / <b>previous</b> to go back."
TF_HINT = "Send <b>True</b> or <b>False</b> — or type <b>next</b> to skip / <b>previous</b> to go back."
SENTENCE_HINT = "Write a sentence using the word — or type <b>next</b> to skip / <b>previous</b> to go back."


async def start_review_for_user(user_id: int, bot, chat_id: int):
    words = get_week_words(user_id)
    if not words:
        await bot.send_message(
            chat_id=chat_id,
            text="📭 No words to review this week!\n\nSend me any word and I'll quiz you next time."
        )
        return
    set_review_state(user_id, words, q_index=0)
    word_list = ", ".join(w.capitalize() for w in words)
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"📚 <b>Weekly Vocab Check!</b>\n\n"
            f"You looked up {len(words)} word(s) this week:\n{word_list}\n\n"
            f"Let's see if they stuck. One question per word.\n\n"
            f"Type <b>next</b> to skip or <b>previous</b> to go back.\n\n"
            f"Ready? Here's your first one 👇"
        ),
        parse_mode="HTML"
    )
    await send_next_question(user_id, bot, chat_id)


async def send_next_question(user_id: int, bot, chat_id: int):
    state = get_review_state(user_id)
    if not state:
        return
    words = state["words"]
    idx = state["q_index"]
    if idx >= len(words):
        await finish_review(user_id, bot, chat_id)
        return
    word = words[idx]
    q = generate_review_question(word, idx)
    text = _format_question(q, idx + 1, len(words))
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    _cache_question(user_id, words, idx, q)


async def handle_review_answer(user_id: int, bot, chat_id: int, user_answer: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT q_index, words_json FROM review_state WHERE user_id = ? AND active = 1",
            (user_id,)
        ).fetchone()

    if not row:
        return False

    idx = row[0]
    state_data = json.loads(row[1])
    words = state_data["words"]
    q = state_data.get("current_q", {})

    if not q:
        return False

    q_type = q.get("type", "")
    word = q.get("word", words[idx] if idx < len(words) else "")
    answer = q.get("answer", "")
    explanation = q.get("explanation", "")
    cleaned = user_answer.strip().lower()

    # ── Navigation ─────────────────────────────────────────────────────────
    if cleaned in NAV_NEXT:
        await bot.send_message(chat_id=chat_id, text="⏭ Skipping...")
        next_idx = idx + 1
        advance_review(user_id, next_idx)
        if next_idx >= len(words):
            await finish_review(user_id, bot, chat_id)
        else:
            _cache_question(user_id, words, next_idx, {})
            await send_next_question(user_id, bot, chat_id)
        return True

    if cleaned in NAV_PREV:
        if idx == 0:
            await bot.send_message(chat_id=chat_id, text="You're already on the first question.")
        else:
            prev_idx = idx - 1
            advance_review(user_id, prev_idx)
            _cache_question(user_id, words, prev_idx, {})
            await bot.send_message(chat_id=chat_id, text="⏮ Going back...")
            await send_next_question(user_id, bot, chat_id)
        return True

    # ── Validate input ──────────────────────────────────────────────────────
    if q_type == "fill-in-the-blank":
        if re.sub(r'[^a-zA-Z]', '', cleaned) not in {"a", "b", "c", "d"}:
            await bot.send_message(chat_id=chat_id, text=FILL_HINT, parse_mode="HTML")
            return True

    elif q_type == "true-or-false":
        if cleaned not in {"true", "false", "t", "f", "yes", "no"}:
            await bot.send_message(chat_id=chat_id, text=TF_HINT, parse_mode="HTML")
            return True

    elif q_type == "write-your-own":
        if len(user_answer.split()) < 3:
            await bot.send_message(chat_id=chat_id, text=SENTENCE_HINT, parse_mode="HTML")
            return True

    # ── Grade ───────────────────────────────────────────────────────────────
    if q_type == "write-your-own":
        grade = grade_sentence(word, user_answer)
        is_correct = grade.get("result") == "CORRECT"
        feedback = grade.get("feedback", "")
    else:
        grade = grade_answer(word, answer, user_answer)
        is_correct = grade["correct"]
        feedback = grade["feedback"]

    emoji = "✅" if is_correct else "❌"
    response = f"{emoji} {feedback}"
    if not is_correct and explanation:
        response += f"\n\n<i>{explanation}</i>"

    await bot.send_message(chat_id=chat_id, text=response, parse_mode="HTML")

    next_idx = idx + 1
    advance_review(user_id, next_idx)
    if next_idx >= len(words):
        await finish_review(user_id, bot, chat_id)
    else:
        _cache_question(user_id, words, next_idx, {})
        await send_next_question(user_id, bot, chat_id)

    return True


async def finish_review(user_id: int, bot, chat_id: int):
    end_review(user_id)
    await bot.send_message(
        chat_id=chat_id,
        text="🎉 Review complete!\n\nKeep looking up words and I'll quiz you next time. 💪"
    )
    settings = get_settings(user_id)
    if settings.get("lesson_enabled", 1):
        await send_lesson(user_id, bot, chat_id)


async def send_lesson(user_id: int, bot, chat_id: int):
    try:
        from datetime import date
        lesson_number = (user_id + date.today().toordinal()) % 20
        lesson = generate_lesson(lesson_number)
        await bot.send_message(chat_id=chat_id, text=lesson, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send lesson to {user_id}: {e}")


def _format_question(q: dict, current: int, total: int) -> str:
    q_type = q.get("type", "")
    word = q.get("word", "").capitalize()
    question = q.get("question", "")
    header = f"<b>Question {current} of {total}</b> — <i>{word}</i>\n\n"

    if q_type == "fill-in-the-blank":
        return header + f"Fill in the blank:\n\n{question}"
    elif q_type == "true-or-false":
        return header + f"<b>True or False?</b>\n\n{question}\n\nReply with <b>True</b> or <b>False</b>."
    elif q_type == "write-your-own":
        return header + f"{question}\n\nSend me your sentence 👇"
    return header + question


def _cache_question(user_id: int, words: list, idx: int, q: dict):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE review_state SET words_json = ?, q_index = ? WHERE user_id = ?",
            (json.dumps({"words": words, "current_q": q}), idx, user_id)
        )
        con.commit()