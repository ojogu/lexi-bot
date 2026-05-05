"""
Lightweight SQLite persistence layer.
Tracks word lookups, review state, and user settings.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from src.config import DB_PATH

MIGRATION_VERSION = 1


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def run_migrations():
    with _conn() as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            try:
                con.execute(
                    "ALTER TABLE word_log ADD COLUMN source TEXT NOT NULL DEFAULT 'lookup'"
                )
            except sqlite3.OperationalError:
                pass
            con.execute("PRAGMA user_version = 1")
            con.commit()


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
                lesson_enabled  INTEGER NOT NULL DEFAULT 1,
                lesson_day      INTEGER NOT NULL DEFAULT 4,
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
        con.commit()


# ── Word log ──────────────────────────────────────────────────────────────────


def log_word(user_id: int, word: str, source: str = "lookup"):
    with _conn() as con:
        con.execute(
            "INSERT INTO word_log (user_id, word, source, looked_up) VALUES (?, ?, ?, ?)",
            (user_id, word.lower(), source, datetime.utcnow().isoformat()),
        )
        con.commit()


def get_week_words(user_id: int) -> list[str]:
    """Return unique words from the last 7 days."""
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? AND looked_up >= ?",
            (user_id, since),
        ).fetchall()
    return [r["word"] for r in rows]


def get_all_user_ids() -> list[int]:
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT user_id FROM word_log").fetchall()
    return [r["user_id"] for r in rows]


# ── Review state ──────────────────────────────────────────────────────────────


def set_review_state(user_id: int, words: list[str], q_index: int = 0):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO review_state (user_id, q_index, words_json, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                q_index    = excluded.q_index,
                words_json = excluded.words_json,
                active     = 1
        """,
            (user_id, q_index, json.dumps(words)),
        )
        con.commit()


def get_review_state(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT q_index, words_json, active FROM review_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row or not row["active"]:
        return None
    return {"q_index": row["q_index"], "words": json.loads(row["words_json"])}


def advance_review(user_id: int, new_index: int):
    with _conn() as con:
        con.execute(
            "UPDATE review_state SET q_index = ? WHERE user_id = ?",
            (new_index, user_id),
        )
        con.commit()


def end_review(user_id: int):
    with _conn() as con:
        con.execute("UPDATE review_state SET active = 0 WHERE user_id = ?", (user_id,))
        con.commit()


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


def get_settings(user_id: int) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        return {**DEFAULT_SETTINGS, "user_id": user_id}
    return dict(row)


def upsert_settings(user_id: int, **kwargs):
    """Update specific settings fields for a user. Creates row if not exists."""
    current = get_settings(user_id)
    current.update(kwargs)
    current["user_id"] = user_id
    if "created_at" not in current:
        current["created_at"] = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
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
        con.commit()


def get_users_by_preference(column: str, value: int) -> list[int]:
    with _conn() as con:
        rows = con.execute(
            f"SELECT user_id FROM user_settings WHERE {column} = ?", (value,)
        ).fetchall()
    return [r["user_id"] for r in rows]


def get_users_for_schedule(
    column_day: str, day_value: int, enabled_column: str
) -> list[int]:
    with _conn() as con:
        rows = con.execute(
            f"SELECT user_id FROM user_settings WHERE {enabled_column} = 1 AND {column_day} = ?",
            (day_value,),
        ).fetchall()
    return [r["user_id"] for r in rows]


# ── Onboarding state ──────────────────────────────────────────────────────────


def set_onboard_state(user_id: int, step: int, active: int = 1):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO onboard_state (user_id, step, active)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                step   = excluded.step,
                active = excluded.active
        """,
            (user_id, step, active),
        )
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
