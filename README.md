# Lexi Bot

A Telegram vocabulary tutor for Nigerian professionals and students.

**Try it:** http://t.me/uselexiBot  
**GitHub:** https://github.com/ojogu/lexi-bot

---

## Features

| Feature | What It Does |
|---|---|
| **Word Lookup** | Send any English word — get a structured definition, pronunciation guide, usage examples, and memory hook in seconds |
| **Spelling Fix** | Send a misspelled word — get the correction with a spelling tip |
| **Word Comparison** | Ask "difference between X and Y" — get a clear breakdown of when to use each |
| **Word Deduction** | Describe a concept ("what's the word for someone who talks too much?") — get the exact word |
| **Quote Explanation** | Paste a quote or saying — get a plain-language breakdown with real-world examples |
| **Audio Pronunciation** | Every word lookup optionally includes a voice note with natural pronunciation via ElevenLabs |
| **Weekly Quiz** | Every Friday (configurable), get quizzed on the words you looked up that week — multiple question types |
| **Grammar Lessons** | After each quiz, receive a short practical English lesson |
| **Word of the Day** | Optional morning word with definition and usage |

---

## Quick Start (Docker)

```fish
# On your VPS
mkdir -p /opt/lexi-bot
cd /opt/lexi-bot

git clone https://github.com/ojogu/lexi-bot .

cp .env.example .env
nano .env  # fill in TELEGRAM_TOKEN and API_KEY

docker compose up -d --build
```

---

## Environment Variables

| Variable | Required | Description | Default |
|---|---|---|---|
| `TELEGRAM_TOKEN` | Yes | Your Telegram bot token from @BotFather | — |
| `API_KEY` | Yes | API key for your LLM provider (OpenAI, Anthropic, Google, etc.) | — |
| `MODEL` | No | LiteLLM model identifier | `anthropic/claude-haiku-4-5` |
| `ELEVENLABS_API_KEY` | Yes | API key from ElevenLabs for text-to-speech | — |
| `ELEVENLABS_VOICE_ID` | Yes | Voice ID from your ElevenLabs voice library | — |
| `REVIEW_HOUR` | No | Hour to send weekly quiz (24-hour format) | `18` |
| `REVIEW_MINUTE` | No | Minute to send weekly quiz | `0` |
| `TIMEZONE` | No | Timezone for scheduled tasks | `Africa/Lagos` |
| `DB_PATH` | No | Path to SQLite database file | `./lexi.db` |

### Switching LLM Provider

Change one line in `.env`:

```bash
# Claude (default)
MODEL=anthropic/claude-haiku-4-5

# OpenAI
MODEL=openai/gpt-4o-mini

# Gemini
MODEL=gemini/gemini-1.5-flash
```

Add the matching API key env var (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.) to your `.env`.

---

## Commands

| Command | What It Does |
|---|---|
| `/start` | Welcome message — kicks off onboarding if new user |
| `/settings` | Change your preferences (Word of Day, audio, quiz, lessons) |
| `/mywords` | See all words you've looked up this week |
| `/help` | How to use the bot |

---

## How It Works

1. **Intent Detection** — Every message is classified by an LLM to route it to the right handler (lookup, spelling, comparison, deduction, or quote explanation)
2. **LiteLLM Integration** — All LLM calls go through LiteLLM, enabling model switching without code changes
3. **SQLite Persistence** — Four tables track users: `word_log`, `review_state`, `user_settings`, `onboard_state`
4. **APScheduler** — Runs Friday review jobs per-user based on their quiz_day preference
5. **ElevenLabs TTS** — Generates pronunciation voice notes in MP3 format for Telegram

---

## Friday Review

Every Friday at 6 PM (configurable), the bot sends each user a quiz on their week's words.

- Three question types rotate: fill-in-the-blank, true/false, write your own sentence
- Navigate with `next` / `previous`
- Wrong answers get a warm correction with the right answer
- After the quiz, a grammar lesson is delivered automatically if enabled

---

## Docker Commands

```fish
docker compose up -d          # Start the bot
docker compose logs -f        # View logs
docker compose restart        # Restart after code changes
docker compose down           # Stop and remove container (data persists in volume)
docker compose up -d --build  # Rebuild after code changes
```

---

## Contributing

Contributions are welcome!

```fish
# Clone and setup
git clone https://github.com/ojogu/lexi-bot
cd lexi-bot
cp .env.example .env

# Lint and typecheck
ruff check .
mypy .

# Run tests (if any)
pytest
```

---

## Project Structure

```
lexi-bot/
├── main.py              # Entry point, bot setup, handler registration
├── src/
│   ├── config.py        # Environment variable loading
│   ├── handlers.py      # Telegram message handlers, callbacks, onboarding
│   ├── lexi.py         # LiteLLM integration, intent detection, prompts
│   ├── prompt.py       # All LLM system prompts (word lookup, quiz, lesson, etc.)
│   ├── review.py       # Quiz logic, answer grading, session state
│   ├── scheduler.py    # APScheduler Friday trigger
│   ├── tts.py          # ElevenLabs text-to-speech
│   └── word_log.py     # SQLite persistence, migrations
├── .env.example         # Template for environment variables
├── Dockerfile           # Multi-stage build with uv
├── docker-compose.yml   # Service definition
├── pyproject.toml       # Project metadata and dependencies
└── requirements.txt     # pip-compatible dependency list
```

---

## License

Open source — feel free to fork, contribute, or build your own version.