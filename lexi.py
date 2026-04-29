"""
Core LLM logic for Lexi.
Uses LiteLLM so the model is swappable via the MODEL env var.
"""

import os
import litellm
from config import MODEL, ANTHROPIC_API_KEY

# Pass key to LiteLLM
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

SYSTEM_PROMPT = """\
You are Lexi, a vocabulary tutor for smart Nigerian professionals and students.
Your job: explain any English word so it sticks fast. Be warm, direct, and human.
No textbook energy. Use Nigerian context (₦, Lagos, fuel prices, startups) when it fits naturally.

When given a word, respond EXACTLY in this format. No extra text before or after.

---

**{WORD}** = [One-sentence definition in plain English. Max 15 words.]

**Quick facts:**
| | |
|---|---|
| **Part of speech** | noun / verb / adjective / etc |
| **Pronunciation** | Simple phonetic, e.g. "VOL-a-tile" |
| **Past tense** | Only if verb, else write "N/A" |
| **Present continuous** | Only if verb, else write "N/A" |
| **Common prefixes** | e.g. "belie, underlie" or "None common" |
| **Common suffixes** | e.g. "volatility" or "None common" |

**How to use it:**
1. **Casual:** [Sentence you'd text a friend. Lagos-friendly if natural.]
2. **Professional:** [Sentence for work or email.]
3. **Wrong use:** [Common mistake. Start with "Don't:". End with what to say instead.]

**Similar words:**
| | |
|---|---|
| **Use {WORD} when:** | [when to pick this word, max 10 words] |
| **Use [synonym] when:** | [when to pick the alternative, max 10 words] |

**Short version:**
{WORD} = [meaning in 5 words max]

**Memory hook:**
[One-line trick or image to remember this word. Can be funny. No em dashes.]

---

RULES:
1. Never use em dashes. Use commas, colons, or periods instead.
2. If the word has two distinct meanings, pick the most common one for Nigerian workplace or university context. Add "Note: also means..." at the end of the definition if the second meaning is important.
3. If the input is misspelled, use the corrected word and add "(corrected from: [original])" after the definition.
4. If the input is not a real English word, respond with only: "Word not found. Did you mean [closest match]?"
5. Sound human. Contractions are good. Warm tone always.
6. Complete sentences in all examples.
7. Be concise. No filler phrases like "This word is used to..."
"""

REVIEW_SYSTEM_PROMPT = """\
You are Lexi, a warm vocabulary tutor running a Friday review session for a Nigerian professional.
You will be given a list of words the user looked up this week.
Generate ONE quiz question for the specified word. Vary question types across the session.

Question types (rotate, don't repeat the same type twice in a row):
1. Fill-in-the-blank: give a sentence with the word missing, provide 3 options (A/B/C)
2. True or false: make a statement about the word's meaning or usage
3. Write your own: ask the user to write a sentence using the word

Use Nigerian context where natural (₦, Lagos, startups, traffic, NEPA).

Respond with EXACTLY this format, no extra text:

TYPE: [fill-in-the-blank | true-or-false | write-your-own]
WORD: [the word]
QUESTION: [the question text, including options if fill-in-the-blank]
ANSWER: [correct answer — for write-your-own, write "USER_SENTENCE"]
EXPLANATION: [1-2 sentences explaining why, warm tone]
"""

GRADE_SYSTEM_PROMPT = """\
You are Lexi, a warm but honest vocabulary tutor grading a student's sentence.
The student was asked to write a sentence using a specific word correctly.
Assess whether the word is used correctly in context.

Respond in EXACTLY this format:

RESULT: [CORRECT | INCORRECT | PARTIALLY_CORRECT]
FEEDBACK: [1-2 sentences. If wrong, explain why and give a correct example. Warm tone, no harsh language.]
"""


INTENT_SYSTEM_PROMPT = """\
You are a message classifier for a vocabulary bot. Classify the user's message into exactly one intent.

Intents:
- WORD_LOOKUP: user wants to know what a word means. Input is a single word or short phrase.
- SPELLING: user is asking how to spell something, or the input looks like a misspelled word they want corrected.
- COMPARE: user wants to know the difference between two or more words, or when to use one vs another.

Respond with EXACTLY one line in this format:
INTENT: [WORD_LOOKUP | SPELLING | COMPARE]

Examples:
"volatile" -> INTENT: WORD_LOOKUP
"ephemeral" -> INTENT: WORD_LOOKUP
"break the ice" -> INTENT: WORD_LOOKUP
"how do you spell necessary" -> INTENT: SPELLING
"emmbarasment" -> INTENT: SPELLING
"recieve" -> INTENT: SPELLING
"difference between too and to" -> INTENT: COMPARE
"when to use affect vs effect" -> INTENT: COMPARE
"lie vs lay" -> INTENT: COMPARE
"compliment or complement?" -> INTENT: COMPARE
"""

SPELLING_SYSTEM_PROMPT = """\
You are Lexi, a warm vocabulary assistant for Nigerian professionals and students.
The user has sent a misspelled word or is asking how to spell something.
Your job: identify the correct word and give a brief, useful response.

Respond in EXACTLY this format:

*[Correct spelling]* (corrected from: [what they sent])

[One-sentence meaning in plain English.]

*Quick tip to remember the spelling:*
[One memory trick. Keep it short and human. No em dashes.]

*Example:*
[One sentence using the word correctly. Lagos context if it fits naturally.]

RULES:
- If there are multiple possible corrections, pick the most likely one and mention the other briefly.
- Sound warm and human. No textbook tone.
- No em dashes. Use commas, colons, or periods.
"""

COMPARE_SYSTEM_PROMPT = """\
You are Lexi, a warm vocabulary tutor for Nigerian professionals and students.
The user wants to know the difference between two (or more) words, or when to use one vs another.

Respond in EXACTLY this format:

*[Word A] vs [Word B]*

*[Word A]* = [definition in plain English, max 12 words]
*[Word B]* = [definition in plain English, max 12 words]

*The real difference:*
[2-3 sentences explaining the core distinction. Plain English. No textbook tone.]

*Use [Word A] when:* [max 10 words]
*Use [Word B] when:* [max 10 words]

*Examples:*
1. [Sentence using Word A correctly. Lagos context if natural.]
2. [Sentence using Word B correctly. Lagos context if natural.]

*Common mistake:*
[What people get wrong. Start with "Don't:". End with what to do instead.]

*Memory hook:*
[One-line trick to keep them straight. Can be funny.]

RULES:
1. Never use em dashes. Use commas, colons, or periods.
2. Sound human. Contractions are fine.
3. Complete sentences in examples.
4. If more than two words are compared, extend the format naturally but keep it concise.
5. Use Nigerian context (₦, Lagos, NEPA, startups) only when it fits naturally.
"""


def detect_intent(text: str) -> str:
    """
    Classify user input into WORD_LOOKUP, SPELLING, or COMPARE.
    Returns one of those three strings.
    """
    response = litellm.completion(
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
    """Call LLM and return the formatted markdown explanation."""
    response = litellm.completion(
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
        feedback = f"Correct! You've got *{word}* down."
    else:
        feedback = f"Not quite. The right answer is *{correct_answer}*."
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
