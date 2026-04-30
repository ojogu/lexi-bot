"""
Friday review session logic.
Generates quiz questions, handles answers, grades responses.
"""

from src.lexi import generate_review_question, grade_sentence, grade_answer
from src.word_log import (
    get_week_words,
    get_all_user_ids,
    set_review_state,
    get_review_state,
    advance_review,
    end_review,
)


def build_intro(words: list[str]) -> str:
    word_list = ", ".join(f"<b>{w.capitalize()}</b>" for w in words)
    return (
        f"📚 <b>Weekly Vocab Check!</b>\n\n"
        f"You looked up {len(words)} word(s) this week: {word_list}\n\n"
        f"Let's see if they stuck. I'll ask one question per word.\n"
        f"Ready? Here's your first one 👇"
    )


def build_no_words_msg() -> str:
    return (
        "📭 No words to review this week!\n\n"
        "Send me any English word to look it up, and I'll quiz you on it next Friday."
    )


async def start_review_for_user(user_id: int, bot, chat_id: int):
    """Called by the scheduler every Friday. Kicks off the review session."""
    words = get_week_words(user_id)
    if not words:
        await bot.send_message(
            chat_id=chat_id, text=build_no_words_msg(), parse_mode="HTML"
        )
        return

    set_review_state(user_id, words, q_index=0)
    intro = build_intro(words)
    await bot.send_message(chat_id=chat_id, text=intro, parse_mode="HTML")

    # Send first question
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

    # Store question data in state for grading
    # We re-use the review_state words_json slot with embedded question cache
    # Simple approach: send question and let handler match by state index
    text = _format_question(q, idx + 1, len(words))
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    # Cache question in DB so grader knows what to compare
    import json
    from src.config import DB_PATH
    import sqlite3

    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """
            UPDATE review_state
            SET words_json = ?
            WHERE user_id = ?
        """,
            (json.dumps({"words": words, "current_q": q}), user_id),
        )
        con.commit()


async def handle_review_answer(user_id: int, bot, chat_id: int, user_answer: str):
    """Called when user sends a message while a review is active."""
    import json, sqlite3
    from src.config import DB_PATH

    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT q_index, words_json FROM review_state WHERE user_id = ? AND active = 1",
            (user_id,),
        ).fetchone()

    if not row:
        return False  # No active review

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

    # Grade the answer
    if q_type == "write-your-own":
        grade = grade_sentence(word, user_answer)
        result = grade.get("result", "INCORRECT")
        feedback = grade.get("feedback", "")
        is_correct = result == "CORRECT"
    else:
        grade = grade_answer(word, q.get("question", ""), answer, user_answer)
        is_correct = grade["correct"]
        feedback = grade["feedback"]

    # Build response
    if is_correct:
        emoji = "✅"
        response = f"{emoji} {feedback}"
    else:
        emoji = "❌"
        response = f"{emoji} {feedback}"
        if explanation:
            response += f"\n\n<i>{explanation}</i>"

    await bot.send_message(chat_id=chat_id, text=response, parse_mode="HTML")

    # Advance to next question
    next_idx = idx + 1
    advance_review(user_id, next_idx)

    if next_idx >= len(words):
        await finish_review(user_id, bot, chat_id)
    else:
        # Update state with new index, clear current_q
        with sqlite3.connect(DB_PATH) as con:
            con.execute(
                """
                UPDATE review_state SET words_json = ?, q_index = ?
                WHERE user_id = ?
            """,
                (json.dumps({"words": words, "current_q": {}}), next_idx, user_id),
            )
            con.commit()
        await send_next_question(user_id, bot, chat_id)

    return True


async def finish_review(user_id: int, bot, chat_id: int):
    end_review(user_id)
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🎉 <b>Review complete!</b>\n\n"
            "That's all your words for this week. Keep looking up new ones and "
            "I'll quiz you again next Friday. You're building something real here. 💪"
        ),
        parse_mode="HTML",
    )


def _format_question(q: dict, current: int, total: int) -> str:
    q_type = q.get("type", "")
    word = q.get("word", "").capitalize()
    question = q.get("question", "")

    header = f"<b>Question {current} of {total}</b> — <i>{word}</i>\n\n"

    if q_type == "fill-in-the-blank":
        return header + f"Fill in the blank:\n{question}"
    elif q_type == "true-or-false":
        return (
            header
            + f"True or False?\n{question}\n\nReply with <b>True</b> or <b>False</b>."
        )
    elif q_type == "write-your-own":
        return header + f"{question}\n\nSend me your sentence 👇"
    else:
        return header + question
