"""
APScheduler setup. Handles daily tasks:
- Morning Word of the Day (8 AM)
- Evening Review Quizzes (6 PM) for users scheduled for "today"
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import REVIEW_HOUR, REVIEW_MINUTE, TIMEZONE
from src.word_log import get_users_for_schedule, get_users_by_preference, log_word
from src.review import start_review_for_user, send_lesson
from src.lexi import word_of_day

logger = logging.getLogger(__name__)


def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # 1. Word of the Day - Every morning at 8:00 AM
    scheduler.add_job(
        _run_morning_wod,
        trigger=CronTrigger(hour=8, minute=0, timezone=TIMEZONE),
        kwargs={"bot": bot},
        id="morning_wod",
        replace_existing=True,
    )

    # 2. Daily Review Trigger - Every evening at configured time
    # This checks which users are scheduled for "today"
    scheduler.add_job(
        _run_daily_reviews,
        trigger=CronTrigger(
            hour=REVIEW_HOUR,
            minute=REVIEW_MINUTE,
            timezone=TIMEZONE,
        ),
        kwargs={"bot": bot},
        id="daily_reviews",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler started with jobs: WOD (08:00), Reviews ({REVIEW_HOUR:02d}:{REVIEW_MINUTE:02d}) {TIMEZONE}"
    )
    return scheduler


async def _run_morning_wod(bot):
    user_ids = await get_users_by_preference("word_of_day", 1)
    if not user_ids:
        return

    logger.info(f"Generating Word of the Day for {len(user_ids)} users")
    try:
        word, html = await word_of_day()
        for user_id in user_ids:
            try:
                await bot.send_message(chat_id=user_id, text=html, parse_mode="HTML")
                await log_word(user_id, word, source="wod")
            except Exception as e:
                logger.error(f"Failed to send WOD to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to generate Word of the Day: {e}")


async def _run_daily_reviews(bot):
    # weekday() returns 0 for Monday, 6 for Sunday
    today_idx = datetime.now().weekday()
    
    # Get users who want a quiz today
    quiz_users = await get_users_for_schedule("quiz_day", today_idx, "quiz_enabled")
    logger.info(f"Running daily reviews for {len(quiz_users)} user(s) (Day Index: {today_idx})")
    
    for user_id in quiz_users:
        try:
            await start_review_for_user(user_id, bot, chat_id=user_id)
        except Exception as e:
            logger.error(f"Failed to start review for {user_id}: {e}")

    # Get users who want a lesson today (if not already handled by quiz finish)
    # Note: finish_review already sends a lesson if enabled. 
    # But if someone has quiz_day != lesson_day, they'd miss it.
    # Let's check for "lesson-only" users today.
    lesson_users = await get_users_for_schedule("lesson_day", today_idx, "lesson_enabled")
    
    # Filter out users who already got a quiz (to avoid double lesson)
    quiz_user_set = set(quiz_users)
    lesson_only = [u for u in lesson_users if u not in quiz_user_set]
    
    if lesson_only:
        logger.info(f"Sending lessons to {len(lesson_only)} lesson-only user(s)")
        for user_id in lesson_only:
            try:
                await send_lesson(user_id, bot, chat_id=user_id)
            except Exception as e:
                logger.error(f"Failed to send lesson to {user_id}: {e}")
