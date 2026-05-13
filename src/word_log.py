"""
Lightweight SQLite persistence layer.
Tracks word lookups, review state, and user settings.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from src.config import DB_PATH


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS word_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                word      TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'lookup',
                looked_up TEXT    NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS review_state (
                user_id     INTEGER PRIMARY KEY,
                q_index     INTEGER NOT NULL DEFAULT 0,
                words_json  TEXT    NOT NULL DEFAULT '[]',
                active      INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id         INTEGER PRIMARY KEY,
                word_of_day     INTEGER NOT NULL DEFAULT 1,
                audio           INTEGER NOT NULL DEFAULT 1,
                quiz_enabled    INTEGER NOT NULL DEFAULT 1,
                quiz_day        INTEGER NOT NULL DEFAULT 4,
                quiz_hour       INTEGER NOT NULL DEFAULT 18,
                quiz_minute     INTEGER NOT NULL DEFAULT 0,
                lesson_enabled  INTEGER NOT NULL DEFAULT 1,
                lesson_day      INTEGER NOT NULL DEFAULT 4,
                lesson_hour     INTEGER NOT NULL DEFAULT 18,
                lesson_minute   INTEGER NOT NULL DEFAULT 30,
                quiz_scope      TEXT    NOT NULL DEFAULT 'weekly',
                week_start      INTEGER NOT NULL DEFAULT 0,
                onboarded       INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS onboard_state (
                user_id  INTEGER PRIMARY KEY,
                step     INTEGER NOT NULL DEFAULT 0,
                active   INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS filter_state (
                user_id    INTEGER PRIMARY KEY,
                step       TEXT    NOT NULL DEFAULT 'start',
                start_date TEXT,
                active     INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Migrate existing rows missing new columns
        for col, definition in [
            ("quiz_hour", "INTEGER NOT NULL DEFAULT 18"),
            ("quiz_minute", "INTEGER NOT NULL DEFAULT 0"),
            ("lesson_hour", "INTEGER NOT NULL DEFAULT 18"),
            ("lesson_minute", "INTEGER NOT NULL DEFAULT 30"),
            ("quiz_scope", "TEXT NOT NULL DEFAULT 'weekly'"),
            ("week_start", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                con.execute(f"ALTER TABLE user_settings ADD COLUMN {col} {definition}")
            except Exception:
                pass
        con.commit()


# ── Word log ──────────────────────────────────────────────────────────────────

def log_word(user_id: int, word: str, source: str = "lookup"):
    with _conn() as con:
        con.execute(
            "INSERT INTO word_log (user_id, word, source, looked_up) VALUES (?, ?, ?, ?)",
            (user_id, word.lower(), source, datetime.utcnow().isoformat())
        )
        con.commit()


def get_week_words(user_id: int) -> list[str]:
    """Return unique words from the current week based on user's week_start setting."""
    settings = get_settings(user_id)
    week_start = settings.get("week_start", 0)
    today = datetime.utcnow()
    days_since_start = (today.weekday() - week_start) % 7
    week_begin = (today - timedelta(days=days_since_start)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? AND looked_up >= ?",
            (user_id, week_begin.isoformat())
        ).fetchall()
    return [r["word"] for r in rows]


def get_words_in_scope(user_id: int) -> list[str]:
    """
    Return words based on the user's quiz_scope setting.
    weekly  -> current week only
    monthly -> last 30 days
    total   -> all words ever
    """
    settings = get_settings(user_id)
    scope = settings.get("quiz_scope", "weekly")
    if scope == "total":
        return get_all_words(user_id)
    elif scope == "monthly":
        return get_words_in_range(
            user_id,
            (datetime.utcnow() - timedelta(days=30)).isoformat(),
            datetime.utcnow().isoformat()
        )
    else:  # weekly
        return get_week_words(user_id)


def get_words_in_range(user_id: int, start: str, end: str) -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? AND looked_up >= ? AND looked_up <= ?",
            (user_id, start, end)
        ).fetchall()
    return [r["word"] for r in rows]


def get_all_words(user_id: int) -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? ORDER BY looked_up DESC",
            (user_id,)
        ).fetchall()
    return [r["word"] for r in rows]


def get_all_words_paginated(user_id: int, page: int = 0, per_page: int = 15) -> tuple[list[str], int]:
    offset = page * per_page
    with _conn() as con:
        total = con.execute(
            "SELECT COUNT(DISTINCT word) FROM word_log WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]
        rows = con.execute(
            """SELECT DISTINCT word FROM word_log WHERE user_id = ?
               ORDER BY MAX(looked_up) DESC LIMIT ? OFFSET ?""",
            (user_id, per_page, offset)
        ).fetchall()
    return [r["word"] for r in rows], total


def get_all_user_ids() -> list[int]:
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT user_id FROM word_log").fetchall()
    return [r["user_id"] for r in rows]


# ── Review state ──────────────────────────────────────────────────────────────

def set_review_state(user_id: int, words: list[str], q_index: int = 0):
    with _conn() as con:
        con.execute("""
            INSERT INTO review_state (user_id, q_index, words_json, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                q_index    = excluded.q_index,
                words_json = excluded.words_json,
                active     = 1
        """, (user_id, q_index, json.dumps(words)))
        con.commit()


def get_review_state(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT q_index, words_json, active FROM review_state WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    if not row or not row["active"]:
        return None
    return {"q_index": row["q_index"], "words": json.loads(row["words_json"])}


def advance_review(user_id: int, new_index: int):
    with _conn() as con:
        con.execute("UPDATE review_state SET q_index = ? WHERE user_id = ?", (new_index, user_id))
        con.commit()


def end_review(user_id: int):
    with _conn() as con:
        con.execute("UPDATE review_state SET active = 0 WHERE user_id = ?", (user_id,))
        con.commit()


# ── User settings ─────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "word_of_day": 1, "audio": 1,
    "quiz_enabled": 1, "quiz_day": 4, "quiz_hour": 18, "quiz_minute": 0,
    "lesson_enabled": 1, "lesson_day": 4, "lesson_hour": 18, "lesson_minute": 30,
    "quiz_scope": "weekly", "week_start": 0, "onboarded": 0,
}


def get_settings(user_id: int) -> dict:
    with _conn() as con:
        row = con.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {**DEFAULT_SETTINGS, "user_id": user_id}
    return dict(row)


def upsert_settings(user_id: int, **kwargs):
    current = get_settings(user_id)
    current.update(kwargs)
    current["user_id"] = user_id
    if "created_at" not in current:
        current["created_at"] = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT INTO user_settings
                (user_id, word_of_day, audio, quiz_enabled, quiz_day, quiz_hour, quiz_minute,
                 lesson_enabled, lesson_day, lesson_hour, lesson_minute,
                 quiz_scope, week_start, onboarded, created_at)
            VALUES
                (:user_id, :word_of_day, :audio, :quiz_enabled, :quiz_day, :quiz_hour, :quiz_minute,
                 :lesson_enabled, :lesson_day, :lesson_hour, :lesson_minute,
                 :quiz_scope, :week_start, :onboarded, :created_at)
            ON CONFLICT(user_id) DO UPDATE SET
                word_of_day    = excluded.word_of_day,
                audio          = excluded.audio,
                quiz_enabled   = excluded.quiz_enabled,
                quiz_day       = excluded.quiz_day,
                quiz_hour      = excluded.quiz_hour,
                quiz_minute    = excluded.quiz_minute,
                lesson_enabled = excluded.lesson_enabled,
                lesson_day     = excluded.lesson_day,
                lesson_hour    = excluded.lesson_hour,
                lesson_minute  = excluded.lesson_minute,
                quiz_scope     = excluded.quiz_scope,
                week_start     = excluded.week_start,
                onboarded      = excluded.onboarded
        """, current)
        con.commit()


def get_users_by_preference(column: str, value: int) -> list[int]:
    with _conn() as con:
        rows = con.execute(
            f"SELECT user_id FROM user_settings WHERE {column} = ?", (value,)
        ).fetchall()
    return [r["user_id"] for r in rows]


def get_users_due_now(feature: str, day: int, hour: int, minute: int) -> list[int]:
    """
    Get users whose scheduled feature is due in the current 30-min slot.
    feature: 'quiz' or 'lesson'
    """
    enabled_col = f"{feature}_enabled"
    day_col = f"{feature}_day"
    hour_col = f"{feature}_hour"
    minute_col = f"{feature}_minute"
    with _conn() as con:
        rows = con.execute(f"""
            SELECT user_id FROM user_settings
            WHERE {enabled_col} = 1
            AND {day_col} = ?
            AND {hour_col} = ?
            AND ({minute_col} BETWEEN ? AND ?)
        """, (day, hour, minute, minute + 29)).fetchall()
    return [r["user_id"] for r in rows]


# ── Onboarding state ──────────────────────────────────────────────────────────

def set_onboard_state(user_id: int, step: int, active: int = 1):
    with _conn() as con:
        con.execute("""
            INSERT INTO onboard_state (user_id, step, active)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET step = excluded.step, active = excluded.active
        """, (user_id, step, active))
        con.commit()


def get_onboard_state(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT step, active FROM onboard_state WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row or not row["active"]:
        return None
    return {"step": row["step"]}


def end_onboarding(user_id: int):
    with _conn() as con:
        con.execute("UPDATE onboard_state SET active = 0 WHERE user_id = ?", (user_id,))
        con.commit()
    upsert_settings(user_id, onboarded=1)


# ── Filter state ──────────────────────────────────────────────────────────────

def set_filter_state(user_id: int, step: str, start_date: str = None):
    with _conn() as con:
        con.execute("""
            INSERT INTO filter_state (user_id, step, start_date, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                step = excluded.step, start_date = excluded.start_date, active = 1
        """, (user_id, step, start_date))
        con.commit()


def get_filter_state(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT step, start_date, active FROM filter_state WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row or not row["active"]:
        return None
    return {"step": row["step"], "start_date": row["start_date"]}


def end_filter_state(user_id: int):
    with _conn() as con:
        con.execute("UPDATE filter_state SET active = 0 WHERE user_id = ?", (user_id,))
        con.commit()