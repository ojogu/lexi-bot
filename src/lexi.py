"""
Core LLM logic for Lexi.
Uses LiteLLM so the model is swappable via the MODEL env var.
"""

import litellm
from src.config import MODEL, API_KEY
from src.prompt import (
    SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    SPELLING_SYSTEM_PROMPT,
    COMPARE_SYSTEM_PROMPT,
    REVIEW_SYSTEM_PROMPT,
    GRADE_SYSTEM_PROMPT,
)


def detect_intent(text: str) -> str:
    """
    Classify user input into WORD_LOOKUP, SPELLING, or COMPARE.
    Returns one of those three strings.
    """
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        temperature=0.0,
        max_tokens=20,
    )
    raw = response.choices[0].message.content.strip()
    for intent in ("WORD_LOOKUP", "SPELLING", "COMPARE"):
        if intent in raw:
            return intent
    return "WORD_LOOKUP"  # safe default


def explain_word(word: str) -> str:
    """Call LLM and return an HTML-formatted word explanation."""
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": word.strip()},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()


def fix_spelling(text: str) -> str:
    """Handle spelling correction requests."""
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": SPELLING_SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        temperature=0.1,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def compare_words(text: str) -> str:
    """Handle word comparison / difference questions."""
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": COMPARE_SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return response.choices[0].message.content.strip()


def generate_review_question(word: str, q_index: int) -> dict:
    """
    Generate a single quiz question for a word.
    Returns a dict: {type, word, question, answer, explanation}
    """
    user_msg = f"Word: {word}\nQuestion number in session: {q_index + 1}"
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=300,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_question(raw)


def grade_sentence(word: str, sentence: str) -> dict:
    """
    Grade a user-written sentence. Returns {result, feedback}.
    result is one of: CORRECT, INCORRECT, PARTIALLY_CORRECT
    """
    user_msg = f"Word: {word}\nStudent's sentence: {sentence}"
    response = litellm.completion(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": GRADE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()
    return _parse_grade(raw)


def grade_answer(word: str, question: str, correct_answer: str, user_answer: str) -> dict:
    """
    Grade a fill-in-the-blank or true/false answer.
    Simple string comparison, no LLM needed.
    Returns {correct: bool, feedback: str}
    """
    is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
    if is_correct:
        feedback = f"Correct! You've got <b>{word}</b> down."
    else:
        feedback = f"Not quite. The right answer is <b>{correct_answer}</b>."
    return {"correct": is_correct, "feedback": feedback}


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_question(raw: str) -> dict:
    result = {}
    for line in raw.splitlines():
        if line.startswith("TYPE:"):
            result["type"] = line.replace("TYPE:", "").strip()
        elif line.startswith("WORD:"):
            result["word"] = line.replace("WORD:", "").strip()
        elif line.startswith("QUESTION:"):
            result["question"] = line.replace("QUESTION:", "").strip()
        elif line.startswith("ANSWER:"):
            result["answer"] = line.replace("ANSWER:", "").strip()
        elif line.startswith("EXPLANATION:"):
            result["explanation"] = line.replace("EXPLANATION:", "").strip()
    return result


def _parse_grade(raw: str) -> dict:
    result = {}
    for line in raw.splitlines():
        if line.startswith("RESULT:"):
            result["result"] = line.replace("RESULT:", "").strip()
        elif line.startswith("FEEDBACK:"):
            result["feedback"] = line.replace("FEEDBACK:", "").strip()
    return result