import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("MODEL", "anthropic/claude-haiku-4-5")
DB_PATH = os.getenv("DB_PATH", "lexi.db")
REVIEW_HOUR = int(os.getenv("REVIEW_HOUR", "18"))   # 6 PM
REVIEW_MINUTE = int(os.getenv("REVIEW_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Africa/Lagos")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set in .env")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set in .env")
