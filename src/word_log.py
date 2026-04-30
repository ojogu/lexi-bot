"""
Lightweight SQLite word log.
Tracks every word a user looks up so the Friday review has data.
"""

import sqlite3
from datetime import datetime, timedelta
from src.config import DB_PATH


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS word_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                word      TEXT    NOT NULL,
                looked_up TEXT    NOT NULL  -- ISO datetime
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS review_state (
                user_id     INTEGER PRIMARY KEY,
                q_index     INTEGER NOT NULL DEFAULT 0,
                words_json  TEXT    NOT NULL DEFAULT '[]',
                active      INTEGER NOT NULL DEFAULT 0  -- 1 = review in progress
            )
        """)
        con.commit()


def log_word(user_id: int, word: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO word_log (user_id, word, looked_up) VALUES (?, ?, ?)",
            (user_id, word.lower(), datetime.utcnow().isoformat())
        )
        con.commit()


def get_week_words(user_id: int) -> list[str]:
    """Return unique words looked up in the last 7 days."""
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT word FROM word_log WHERE user_id = ? AND looked_up >= ?",
            (user_id, since)
        ).fetchall()
    return [r[0] for r in rows]


def get_all_user_ids() -> list[int]:
    """Return every user who has ever looked up a word."""
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT user_id FROM word_log").fetchall()
    return [r[0] for r in rows]


# ── Review state helpers ──────────────────────────────────────────────────────

import json


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
    if not row or not row[2]:
        return None
    return {"q_index": row[0], "words": json.loads(row[1])}


def advance_review(user_id: int, new_index: int):
    with _conn() as con:
        con.execute(
            "UPDATE review_state SET q_index = ? WHERE user_id = ?",
            (new_index, user_id)
        )
        con.commit()


def end_review(user_id: int):
    with _conn() as con:
        con.execute(
            "UPDATE review_state SET active = 0 WHERE user_id = ?",
            (user_id,)
        )
        con.commit()
