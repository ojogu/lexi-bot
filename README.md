# Lexi Bot

A Telegram vocabulary tutor for Nigerian professionals and students. Lexi explains words, fixes spelling, compares similar words, and quizzes users weekly — all through a conversational interface.

---

## The Problem

 professionals and students in Nigeria often encounter English words they don't know — in articles, meetings, or exams. Searching Google takes time, definitions are often confusing, and there's no way to retain new vocabulary over time. Lexi solves this by providing instant, context-rich explanations tailored for Nigerian speakers, with pronunciation audio, spaced repetition quizzes, and built-in grammar lessons.

---

## Key Features

- **Word Lookup** — Send any word and get a definition, pronunciation, usage in casual and professional contexts, common mistakes, synonyms, and a memory hook in seconds.
- **Spelling Fix** — Send a misspelled word and receive the correction with a practical spelling tip.
- **Word Comparison** — Ask "difference between X and Y" and receive a clear breakdown of when to use each word.
- **Word Deduction** — Describe a concept ("what's the word for someone who talks too much?") and get the exact word.
- **Quote Explanation** — Paste a quote or saying and receive a plain-language breakdown with real-world examples.
- **Audio Pronunciation** — Every word lookup optionally includes a voice note with natural pronunciation via ElevenLabs text-to-speech.
- **Weekly Quiz** — Every Friday (configurable), each user receives a quiz on their looked-up words with multiple question types and immediate feedback.
- **Grammar Lessons** — After each quiz, a short practical English lesson is delivered covering topics like affect/effect, punctuation, and sentence structure.

---

## Tech Stack

| Layer | Technology | Why |
|-------|------------|-----|
| Bot Framework | python-telegram-bot 21.x | Official Python library for Telegram Bot API; supports async handlers and callbacks natively. |
| LLM Integration | LiteLLM 1.48.x | Unifies OpenAI, Anthropic, Google, and other providers behind a single API. Switch models via one env var without code changes. |
| Task Scheduling | APScheduler 3.10.x | Runs weekly quiz triggers per-user in-process without external workers. |
| Database | SQLite | Zero-config, file-based persistence. Suits single-instance deployments; data lives in a mapped volume. |
| Text-to-Speech | ElevenLabs | High-quality neural voices in MP3 format for Telegram voice messages. |
| Deployment | Docker + Docker Compose | Single-command bring-up; containerized Python 3.12 with uv for fast dependency resolution. |

---

## System Architecture

```
User Message
      │
      ▼
┌─────────────────┐
│  Intent Detector  │   (LiteLLM classifies: lookup, spelling, compare, deduction, quote)
│    (lexi.py)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   LLM Response   │   (Structured reply via LiteLLM with Nigerian context prompts)
│   (lexi.py)      │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│  TTS  │ │  DB   │
│  (tts)│ │(sqlite)│
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
┌─────────────────┐
│   Telegram      │   (Voice note or text reply)
│  User Output    │
└─────────────────┘
```

Full architecture and database schema are documented in `docs/`.

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- LLM API key (OpenAI, Anthropic, Google, etc.)
- ElevenLabs API key and voice ID from your ElevenLabs dashboard

### Clone and Setup

```fish
git clone https://github.com/ojogu/lexi-bot
cd lexi-bot
cp .env.example .env
nano .env  # fill in TELEGRAM_TOKEN, API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
docker compose up -d --build
```

### Access Points

| Service | URL |
|---------|-----|
| Telegram Bot | `t.me/uselexiBot` |
| Logs | `docker compose logs -f` |
| Database (local) | `./lexi.db` |

---

## Project Structure

```
lexi-bot/
├── main.py                 # Entry point, bot initialization
├── docker-compose.yml     # Single-service container definition
├── Dockerfile            # Multi-stage build with uv
├── pyproject.toml        # Project metadata and dependencies
├── requirements.txt    # pip-compatible dependency list
├── .env.example        # Environment template
├── docs/               # Architecture and database docs
└── src/
    ├── config.py        # Environment variable loading and validation
    ├── handlers.py     # Telegram message handlers, callbacks, onboarding UI
    ├── lexi.py         # LiteLLM integration, intent detection, LLM prompts
    ├── prompt.py      # All system prompts (word lookup, quiz, lesson, etc.)
    ├── review.py      # Quiz logic, answer grading, session state, lesson delivery
    ├── scheduler.py   # APScheduler weekly triggers
    ├── tts.py          # ElevenLabs text-to-speech wrapper
    └── word_log.py    # SQLite persistence layer, migrations
```

---

## Development Commands

```fish
ruff check .     # Lint
mypy .           # Typecheck
pytest          # Run tests
```

---

## Real Engineering Challenges

**Intent Detection Drift** — Early versions of Lexi misclassified user queries (e.g., "difference between X and Y" as a lookup instead of COMPARE). Solved by adding explicit examples in the `INTENT_SYSTEM_PROMPT` at `src/prompt.py:63-93` and lowering the temperature to 0.0 for deterministic results.

**Scheduler Timezone Bugs** — Users in different timezones received quizzes at the wrong hour. Fixed by persisting user-specific `quiz_day` (0-6) in SQLite and having APScheduler trigger based on the server hour, with the client timezone handled at display time. This is visible in `src/scheduler.py` and `src/word_log.py`.

Full incident reports and architectural decisions are documented in `docs/`.

---

## Contact & License

- **Try it:** https://t.me/uselexiBot
- **GitHub:** https://github.com/ojogu/lexi-bot

Open source — feel free to fork, contribute, or build your own version.