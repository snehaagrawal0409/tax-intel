"""
src/state_manager.py — SQLite dedup with JSON fallback for CI persistence
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

from config.settings import DB_PATH, JSON_BACKUP, STATE_DIR
from src.logger import get_logger

logger = get_logger("state_manager")


def _ensure_db() -> sqlite3.Connection:
    os.makedirs(STATE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_items (
            unique_id   TEXT PRIMARY KEY,
            source_type TEXT,
            title       TEXT,
            seen_at     TEXT
        )
    """)
    conn.commit()
    return conn


def is_seen(unique_id: str) -> bool:
    if not unique_id:
        return False
    try:
        conn = _ensure_db()
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.warning(f"is_seen DB error: {e}")
        return False


def mark_seen(unique_id: str, source_type: str = "", title: str = "") -> None:
    if not unique_id:
        return
    try:
        conn = _ensure_db()
        conn.execute(
            "INSERT OR REPLACE INTO seen_items (unique_id, source_type, title, seen_at) "
            "VALUES (?, ?, ?, ?)",
            (unique_id, source_type, title[:300], datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"mark_seen DB error: {e}")

    # Also update JSON backup
    _update_json_backup(unique_id, source_type, title)


def _update_json_backup(unique_id: str, source_type: str, title: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        data: dict = {}
        if os.path.exists(JSON_BACKUP):
            with open(JSON_BACKUP, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[unique_id] = {
            "source_type": source_type,
            "title":       title[:300],
            "seen_at":     datetime.now(timezone.utc).isoformat(),
        }
        with open(JSON_BACKUP, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"JSON backup update error: {e}")


def restore_from_json_if_empty() -> None:
    """Called at startup: if SQLite is empty, restore from JSON backup (CI cache miss)."""
    if not os.path.exists(JSON_BACKUP):
        logger.info("No JSON backup found — starting fresh")
        return
    try:
        conn = _ensure_db()
        count = conn.execute("SELECT COUNT(*) FROM seen_items").fetchone()[0]
        if count > 0:
            logger.info(f"SQLite has {count} items — skip restore")
            conn.close()
            return

        with open(JSON_BACKUP, "r", encoding="utf-8") as f:
            data: dict = json.load(f)

        restored = 0
        for uid, meta in data.items():
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO seen_items (unique_id, source_type, title, seen_at) "
                    "VALUES (?, ?, ?, ?)",
                    (uid, meta.get("source_type", ""), meta.get("title", ""), meta.get("seen_at", "")),
                )
                restored += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        logger.info(f"Restored {restored} items from JSON backup into SQLite")
    except Exception as e:
        logger.warning(f"restore_from_json_if_empty error: {e}")
