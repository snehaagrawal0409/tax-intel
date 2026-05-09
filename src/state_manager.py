"""
src/state_manager.py
Persistent deduplication using SQLite + JSON backup.
Survives CI/container restarts when state/ dir is cached or committed.
"""

import json
import os
import sqlite3
import time
from typing import Set

from config.settings import STATE_DB_PATH, STATE_JSON_BACKUP
from src.logger import get_logger

logger = get_logger("state_manager")


def _ensure_dirs():
    os.makedirs(os.path.dirname(STATE_DB_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(STATE_JSON_BACKUP), exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_items (
            unique_id   TEXT PRIMARY KEY,
            source_type TEXT,
            heading     TEXT,
            first_seen  REAL
        )
        """
    )
    conn.commit()
    return conn


def is_seen(unique_id: str) -> bool:
    """Return True if unique_id has been processed before."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE unique_id = ?", (unique_id,)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.error(f"State check failed for {unique_id}: {e}")
        return False  # fail-open: process the item to avoid missing it


def mark_seen(unique_id: str, source_type: str = "", heading: str = ""):
    """Mark a unique_id as processed."""
    try:
        conn = _get_conn()
        conn.execute(
            """
            INSERT OR IGNORE INTO seen_items (unique_id, source_type, heading, first_seen)
            VALUES (?, ?, ?, ?)
            """,
            (unique_id, source_type, heading[:200], time.time()),
        )
        conn.commit()
        conn.close()
        _sync_json_backup()
    except Exception as e:
        logger.error(f"Failed to mark {unique_id} as seen: {e}")


def get_all_seen() -> Set[str]:
    """Return set of all seen unique IDs."""
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT unique_id FROM seen_items").fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception as e:
        logger.error(f"Failed to get all seen items: {e}")
        return set()


def _sync_json_backup():
    """Write JSON backup of all seen IDs (useful for committing to git)."""
    try:
        seen = get_all_seen()
        _ensure_dirs()
        with open(STATE_JSON_BACKUP, "w") as f:
            json.dump(sorted(seen), f, indent=2)
    except Exception as e:
        logger.warning(f"JSON backup sync failed: {e}")


def restore_from_json_if_empty():
    """
    On fresh CI run where SQLite is missing but JSON backup is committed,
    restore state from JSON so we don't re-process old items.
    """
    seen = get_all_seen()
    if seen:
        return  # SQLite already has data

    if not os.path.exists(STATE_JSON_BACKUP):
        return

    try:
        with open(STATE_JSON_BACKUP) as f:
            ids = json.load(f)
        conn = _get_conn()
        for uid in ids:
            conn.execute(
                "INSERT OR IGNORE INTO seen_items (unique_id, source_type, heading, first_seen) VALUES (?,?,?,?)",
                (uid, "restored", "", time.time()),
            )
        conn.commit()
        conn.close()
        logger.info(f"Restored {len(ids)} seen IDs from JSON backup")
    except Exception as e:
        logger.error(f"Failed to restore from JSON backup: {e}")
