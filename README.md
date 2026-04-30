# Lexi Bot

A Telegram vocabulary tutor for Nigerian professionals and students.
Send it any English word, get a clean breakdown in seconds.
Every Friday it quizzes you on the words you looked up that week.

---

## Local Setup

```fish
git clone <your-repo> lexi-bot
cd lexi-bot

python -m venv venv
source venv/bin/activate.fish   # fish shell

pip install -r requirements.txt

cp .env.example .env
# Fill in TELEGRAM_TOKEN and API_KEY in .env

python main.py
```

---

## VPS Deployment (Docker)

```fish
# On your VPS
mkdir -p /opt/lexi-bot
cd /opt/lexi-bot

git clone <your-repo> .

cp .env.example .env
nano .env  # fill in TELEGRAM_TOKEN and API_KEY

# Build and run
docker compose up -d

# Check logs
docker compose logs -f
```

That's it. The container restarts automatically on crash or VPS reboot.

### Useful commands

```fish
docker compose stop        # stop the bot
docker compose start       # start it again
docker compose restart     # restart after a code change
docker compose down        # stop and remove container (data is safe in volume)
docker compose up -d --build  # rebuild image after code changes
```

---

## Switching LLM Provider

Change one line in `.env`:

```
# Claude (default)
MODEL=anthropic/claude-haiku-4-5

# OpenAI
MODEL=openai/gpt-4o-mini

# Gemini
MODEL=gemini/gemini-1.5-flash
```

Add the matching API key env var (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc).

---

## Commands

| Command | What it does |
|---|---|
| `/start` | Welcome message |
| `/help` | How to use the bot |
| `/mywords` | See your words for this week |

---

## Friday Review

Every Friday at 6 PM Lagos time, the bot sends each user a quiz on their week's words.
Three question types rotate: fill-in-the-blank, true/false, write your own sentence.
Wrong answers get a warm correction and the right answer.

---

## Project Structure

```
lexi-bot/
├── main.py          # Entry point, bot setup
├── handlers.py      # Telegram message handlers
├── lexi.py          # LiteLLM integration, prompts
├── review.py        # Friday quiz logic
├── word_log.py      # SQLite word tracker
├── scheduler.py     # APScheduler Friday trigger
├── config.py        # Env var loading
├── .env.example     # Template
├── requirements.txt
└── lexi-bot.service # systemd unit
```
