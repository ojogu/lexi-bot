"""
APScheduler setup. Fires the Friday review for every registered user.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import REVIEW_HOUR, REVIEW_MINUTE, TIMEZONE
from src.word_log import get_all_user_ids
from src.review import start_review_for_user

logger = logging.getLogger(__name__)


def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        _run_friday_review,
        trigger=CronTrigger(
            day_of_week="fri",
            hour=REVIEW_HOUR,
            minute=REVIEW_MINUTE,
            timezone=TIMEZONE,
        ),
        kwargs={"bot": bot},
        id="friday_review",
        replace_existing=True,
    )

    logger.info(
        f"Friday review scheduled: every Friday at {REVIEW_HOUR:02d}:{REVIEW_MINUTE:02d} {TIMEZONE}"
    )
    return scheduler


async def _run_friday_review(bot):
    user_ids = get_all_user_ids()
    logger.info(f"Starting Friday review for {len(user_ids)} user(s)")
    for user_id in user_ids:
        try:
            # chat_id == user_id for private chats (DM bots)
            await start_review_for_user(user_id, bot, chat_id=user_id)
        except Exception as e:
            logger.error(f"Failed to send review to user {user_id}: {e}")
