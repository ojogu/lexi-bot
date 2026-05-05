"""
Core LLM logic for Lexi.
Uses LiteLLM so the model is swappable via the MODEL env var.
"""

import re
import litellm
from src.config import MODEL, API_KEY
from src.prompt import (
    SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT, SPELLING_SYSTEM_PROMPT,
    COMPARE_SYSTEM_PROMPT, DEDUCTION_SYSTEM_PROMPT,
    QUOTE_EXPLANATION_SYSTEM_PROMPT, WORD_OF_DAY_SYSTEM_PROMPT,
    LESSON_SYSTEM_PROMPT, REVIEW_SYSTEM_PROMPT, GRADE_SYSTEM_PROMPT,
)


def _call(system: str, user: str, temperature: float = 0.2, max_tokens: int = 600) -> str:
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user.strip()},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def detect_intent(text: str) -> str:
    raw = _call(INTENT_SYSTEM_PROMPT, text, temperature=0.0, max_tokens=20)
    for intent in ("WORD_DEDUCTION", "QUOTE_EXPLANATION", "SPELLING", "COMPARE", "WORD_LOOKUP"):
        if intent in raw:
            return intent
    return "WORD_LOOKUP"


def explain_word(word: str) -> str:
    return _call(SYSTEM_PROMPT, word)


def fix_spelling(text: str) -> str:
    return _call(SPELLING_SYSTEM_PROMPT, text, temperature=0.1, max_tokens=300)


def compare_words(text: str) -> str:
    return _call(COMPARE_SYSTEM_PROMPT, text)


def deduce_word(text: str) -> tuple[str, str]:
    raw = _call(DEDUCTION_SYSTEM_PROMPT, text, temperature=0.3)
    word = ""
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("WORD:"):
            word = line.replace("WORD:", "").strip()
            raw = "\n".join(lines[i + 1:]).strip()
            break
    return word, raw


def explain_quote(text: str) -> str:
    return _call(QUOTE_EXPLANATION_SYSTEM_PROMPT, text, temperature=0.3, max_tokens=500)


def word_of_day() -> tuple[str, str]:
    raw = _call(WORD_OF_DAY_SYSTEM_PROMPT, "Give me today's word.", temperature=0.9)
    match = re.search(r'<b>([^<]+)</b>\s*\n\s*<i>', raw)
    word = match.group(1).strip() if match else "word"
    word = word.replace("🌟 Word of the Day", "").strip()
    return word, raw


def generate_lesson(lesson_number: int) -> str:
    return _call(
        LESSON_SYSTEM_PROMPT,
        f"lesson_number: {lesson_number}",
        temperature=0.5,
        max_tokens=500,
    )


def generate_review_question(word: str, q_index: int) -> dict:
    raw = _call(
        REVIEW_SYSTEM_PROMPT,
        f"Word: {word}\nQuestion number in session: {q_index + 1}",
        temperature=0.4,
        max_tokens=400,
    )
    return _parse_question(raw)


def grade_sentence(word: str, sentence: str) -> dict:
    raw = _call(
        GRADE_SYSTEM_PROMPT,
        f"Word: {word}\nStudent's sentence: {sentence}",
        max_tokens=200,
    )
    return _parse_grade(raw)


def grade_answer(word: str, correct_answer: str, user_answer: str) -> dict:
    clean_user = re.sub(r'[^a-zA-Z]', '', user_answer.strip()).lower()
    clean_correct = re.sub(r'[^a-zA-Z]', '', correct_answer.strip()).lower()

    true_aliases = {"true", "t", "yes", "correct"}
    false_aliases = {"false", "f", "no", "incorrect"}

    if clean_correct in true_aliases:
        is_correct = clean_user in true_aliases
    elif clean_correct in false_aliases:
        is_correct = clean_user in false_aliases
    else:
        is_correct = clean_user == clean_correct

    feedback = (
        f"Correct! You've got <b>{word}</b> down."
        if is_correct
        else f"Not quite. The right answer is <b>{correct_answer}</b>."
    )
    return {"correct": is_correct, "feedback": feedback}


def _parse_question(raw: str) -> dict:
    result = {}
    option_lines = []
    in_options = False

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("TYPE:"):
            result["type"] = stripped.replace("TYPE:", "").strip()
            in_options = False
        elif stripped.startswith("WORD:"):
            result["word"] = stripped.replace("WORD:", "").strip()
            in_options = False
        elif stripped.startswith("QUESTION:"):
            result["question"] = stripped.replace("QUESTION:", "").strip()
            in_options = True  # options follow question
        elif stripped.startswith("ANSWER:"):
            result["answer"] = stripped.replace("ANSWER:", "").strip()
            in_options = False
        elif stripped.startswith("EXPLANATION:"):
            result["explanation"] = stripped.replace("EXPLANATION:", "").strip()
            in_options = False
        elif in_options and re.match(r'^[A-D]\.', stripped):
            option_lines.append(stripped)

    if option_lines:
        result["question"] = result.get("question", "") + "\n\n" + "\n".join(option_lines)

    return result


def _parse_grade(raw: str) -> dict:
    result = {}
    for line in raw.splitlines():
        if line.startswith("RESULT:"):
            result["result"] = line.replace("RESULT:", "").strip()
        elif line.startswith("FEEDBACK:"):
            result["feedback"] = line.replace("FEEDBACK:", "").strip()
    return result