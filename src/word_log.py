"""
Lightweight SQLite persistence layer.
Tracks word lookups, review state, and user settings.
"""

import json
import aiosqlite
from datetime import datetime, timedelta, timezone
from src.config import DB_PATH

MIGRATION_VERSION = 1


async def run_migrations():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
            version = row[0] if row else 0

        if version < 1:
            try:
                await db.execute(
                    "ALTER TABLE word_log ADD COLUMN source TEXT NOT NULL DEFAULT 'lookup'"
                )
            except aiosqlite.OperationalError:
                pass
            await db.execute("PRAGMA user_version = 1")
            await db.commit()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS word_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                word      TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'lookup',
                looked_up TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS review_state (
                user_id     INTEGER PRIMARY KEY,
                q_index     INTEGER NOT NULL DEFAULT 0,
                words_json  TEXT    NOT NULL DEFAULT '[]',
                active      INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id         INTEGER PRIMARY KEY,
                word_of_day     INTEGER NOT NULL DEFAULT 1,
                audio           INTEGER NOT NULL DEFAULT 1,
                quiz_enabled    INTEGER NOT NULL DEFAULT 1,
                quiz_day        INTEGER NOT NULL DEFAULT 4,
                lesson_enabled  INTEGER NOT NULL DEFAULT 1,
                lesson_day      INTEGER NOT NULL DEFAULT 4,
                onboarded       INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS onboard_state (
                user_id  INTEGER PRIMARY KEY,
                step     INTEGER NOT NULL DEFAULT 0,
                active   INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()


# ── Word log ──────────────────────────────────────────────────────────────────


async def log_word(user_id: int, word: str, source: str = "lookup"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO word_log (user_id, word, source, looked_up) VALUES (?, ?, ?, ?)",
            (user_id, word.lower(), source, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()


async def get_week_words(user_id: int) -> list[str]:
    """Return unique words from the last 7 days."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? AND looked_up >= ?",
            (user_id, since),
        ) as cursor:
            rows = await cursor.fetchall()
    return [r["word"] for r in rows]


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT DISTINCT user_id FROM word_log") as cursor:
            rows = await cursor.fetchall()
    return [r["user_id"] for r in rows]


# ── Review state ──────────────────────────────────────────────────────────────


async def set_review_state(user_id: int, words: list[str], q_index: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO review_state (user_id, q_index, words_json, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                q_index    = excluded.q_index,
                words_json = excluded.words_json,
                active     = 1
        """,
            (user_id, q_index, json.dumps({"words": words})),
        )
        await db.commit()


async def get_review_state(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT q_index, words_json, active FROM review_state WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if not row or not row["active"]:
        return None
    
    data = json.loads(row["words_json"])
    # words_json could be a list (legacy) or a dict (new)
    words = data["words"] if isinstance(data, dict) else data
    return {"q_index": row["q_index"], "words": words}


async def advance_review(user_id: int, new_index: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE review_state SET q_index = ? WHERE user_id = ?",
            (new_index, user_id),
        )
        await db.commit()


async def end_review(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE review_state SET active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


# ── User settings ─────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "word_of_day": 1,
    "audio": 1,
    "quiz_enabled": 1,
    "quiz_day": 4,
    "lesson_enabled": 1,
    "lesson_day": 4,
    "onboarded": 0,
}


async def get_settings(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return {**DEFAULT_SETTINGS, "user_id": user_id}
    return dict(row)


async def upsert_settings(user_id: int, **kwargs):
    """Update specific settings fields for a user. Creates row if not exists."""
    current = await get_settings(user_id)
    current.update(kwargs)
    current["user_id"] = user_id
    if "created_at" not in current:
        current["created_at"] = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_settings
                (user_id, word_of_day, audio, quiz_enabled, quiz_day,
                 lesson_enabled, lesson_day, onboarded, created_at)
            VALUES
                (:user_id, :word_of_day, :audio, :quiz_enabled, :quiz_day,
                 :lesson_enabled, :lesson_day, :onboarded, :created_at)
            ON CONFLICT(user_id) DO UPDATE SET
                word_of_day    = excluded.word_of_day,
                audio          = excluded.audio,
                quiz_enabled   = excluded.quiz_enabled,
                quiz_day       = excluded.quiz_day,
                lesson_enabled = excluded.lesson_enabled,
                lesson_day     = excluded.lesson_day,
                onboarded      = excluded.onboarded
        """,
            current,
        )
        await db.commit()


async def get_users_by_preference(column: str, value: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT user_id FROM user_settings WHERE {column} = ?", (value,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [r["user_id"] for r in rows]


async def get_users_for_schedule(
    column_day: str, day_value: int, enabled_column: str
) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT user_id FROM user_settings WHERE {enabled_column} = 1 AND {column_day} = ?",
            (day_value,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [r["user_id"] for r in rows]


# ── Onboarding state ──────────────────────────────────────────────────────────


async def set_onboard_state(user_id: int, step: int, active: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO onboard_state (user_id, step, active)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                step   = excluded.step,
                active = excluded.active
        """,
            (user_id, step, active),
        )
        await db.commit()


async def get_onboard_state(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT step, active FROM onboard_state WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row or not row["active"]:
        return None
    return {"step": row["step"]}


async def end_onboarding(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE onboard_state SET active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()
    await upsert_settings(user_id, onboarded=1)
