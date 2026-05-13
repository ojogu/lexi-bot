"""
APScheduler setup.
Runs every 10 minutes and fires features for users whose scheduled time matches.
Handles per-user day + time settings correctly.
"""

import logging
import sqlite3
from datetime import date, datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import TIMEZONE, DB_PATH
from src.word_log import get_users_by_preference, get_users_due_now, log_word
from src.lexi import word_of_day
from src.review import start_review_for_user, send_lesson

logger = logging.getLogger(__name__)


def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Word of the day — every day at 8 AM
    scheduler.add_job(
        _send_word_of_day,
        trigger=CronTrigger(hour=8, minute=0, timezone=TIMEZONE),
        kwargs={"bot": bot},
        id="word_of_day",
        replace_existing=True,
    )

    # Tick every 10 minutes — checks who is due for quiz or lesson
    scheduler.add_job(
        _tick,
        trigger=CronTrigger(minute="0,10", timezone=TIMEZONE),
        kwargs={"bot": bot},
        id="tick",
        replace_existing=True,
    )

    logger.info("Scheduler started: WOD @ 8AM, tick every 10min")
    return scheduler


async def _send_word_of_day(bot):
    user_ids = get_users_by_preference("word_of_day", 1)
    logger.info(f"Sending word of the day to {len(user_ids)} user(s)")
    for user_id in user_ids:
        try:
            word, explanation = word_of_day()
            log_word(user_id, word, source="word_of_day")
            await bot.send_message(chat_id=user_id, text=explanation, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send WOD to {user_id}: {e}")


async def _tick(bot):
    """
    Runs every 10 minutes.
    Checks which users are due for quiz or lesson this slot and fires for them.
    """
    now = datetime.now()
    today = date.today().weekday()  # 0=Mon, 6=Sun
    hour = now.hour
    slot = 0 if now.minute < 10 else 10

    logger.info(f"Tick: weekday={today} hour={hour} slot={slot}")

    # Quiz
    quiz_users = get_users_due_now("quiz", today, hour, slot)
    logger.info(f"Quiz due for {len(quiz_users)} user(s)")
    for user_id in quiz_users:
        try:
            await start_review_for_user(user_id, bot, chat_id=user_id)
        except Exception as e:
            logger.error(f"Failed quiz for {user_id}: {e}")

    # Standalone lesson (only for users whose lesson day != quiz day)
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("""
            SELECT user_id FROM user_settings
            WHERE lesson_enabled = 1
            AND lesson_day = ?
            AND lesson_hour = ?
            AND (lesson_minute BETWEEN ? AND ?)
            AND lesson_day != quiz_day
        """, (today, hour, slot, slot + 29)).fetchall()
    lesson_users = [r[0] for r in rows]
    logger.info(f"Standalone lesson due for {len(lesson_users)} user(s)")
    for user_id in lesson_users:
        try:
            await send_lesson(user_id, bot, chat_id=user_id)
        except Exception as e:
            logger.error(f"Failed lesson for {user_id}: {e}")