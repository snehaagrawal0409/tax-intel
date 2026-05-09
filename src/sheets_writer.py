"""
src/sheets_writer.py
Writes structured data to Google Sheets.
Uses gspread with service account credentials.
Handles duplicate prevention, append reliability, and tab management.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

from config.settings import (
    GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEET_ID,
    SHEET_COLUMNS, SOURCES
)
from src.logger import get_logger

logger = get_logger("sheets_writer")

_gc = None          # gspread client (lazily initialized)
_spreadsheet = None # gspread Spreadsheet object


def _init_client():
    """Initialize gspread client using service account credentials."""
    global _gc, _spreadsheet
    if _gc:
        return True

    if not GOOGLE_SHEETS_CREDENTIALS:
        logger.error("GOOGLE_SHEETS_CREDENTIALS not set")
        return False
    if not GOOGLE_SHEET_ID:
        logger.error("GOOGLE_SHEET_ID not set")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        _gc = gspread.authorize(creds)
        _spreadsheet = _gc.open_by_key(GOOGLE_SHEET_ID)
        logger.info("Google Sheets client initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Google Sheets client: {e}")
        return False


def _get_or_create_worksheet(tab_name: str):
    """Get existing worksheet or create new one with headers."""
    global _spreadsheet
    try:
        ws = _spreadsheet.worksheet(tab_name)
        # Ensure headers exist
        headers = ws.row_values(1)
        if not headers:
            ws.insert_row(SHEET_COLUMNS, 1)
            logger.info(f"Added headers to existing tab: {tab_name}")
        return ws
    except Exception:
        # Worksheet doesn't exist — create it
        try:
            ws = _spreadsheet.add_worksheet(title=tab_name, rows=2000, cols=len(SHEET_COLUMNS))
            ws.insert_row(SHEET_COLUMNS, 1)
            logger.info(f"Created new tab: {tab_name}")
            return ws
        except Exception as e:
            logger.error(f"Failed to create worksheet {tab_name}: {e}")
            return None


def _get_existing_ids(ws) -> set:
    """Get all unique IDs already in the sheet (column 7 = Unique ID)."""
    try:
        col_idx = SHEET_COLUMNS.index("Unique ID") + 1  # 1-indexed
        existing = ws.col_values(col_idx)
        return set(existing[1:])  # skip header
    except Exception as e:
        logger.warning(f"Could not read existing IDs: {e}")
        return set()


def append_item(item: Dict, tab_name: str) -> bool:
    """
    Append a single item row to the specified tab.
    Skips if unique_id already exists in sheet.
    Returns True on success.
    """
    if not _init_client():
        return False

    ws = _get_or_create_worksheet(tab_name)
    if not ws:
        return False

    # Check for duplicates in sheet
    existing_ids = _get_existing_ids(ws)
    if item.get("unique_id") in existing_ids:
        logger.debug(f"Item already in sheet: {item.get('unique_id')}")
        return True  # not an error

    row = [
        item.get("date", ""),
        item.get("title", "")[:500],
        item.get("summary", "")[:1000],
        item.get("sections_str", ""),
        item.get("url", ""),
        item.get("source_type", ""),
        item.get("unique_id", ""),
        item.get("scraped_at", datetime.utcnow().isoformat()),
    ]

    for attempt in range(1, 4):
        try:
            ws.append_row(row, value_input_option="USER_ENTERED")
            logger.debug(f"Appended to sheet tab '{tab_name}': {item.get('unique_id')}")
            return True
        except Exception as e:
            logger.warning(f"Sheet append attempt {attempt} failed: {e}")
            if attempt < 3:
                time.sleep(3)

    logger.error(f"Failed to append item to sheet after 3 attempts: {item.get('unique_id')}")
    return False


def append_batch(items: List[Dict], tab_name: str) -> int:
    """
    Append multiple items to a sheet tab.
    Returns count of successfully appended items.
    """
    if not items:
        return 0
    if not _init_client():
        return 0

    ws = _get_or_create_worksheet(tab_name)
    if not ws:
        return 0

    existing_ids = _get_existing_ids(ws)
    new_rows = []
    for item in items:
        if item.get("unique_id") in existing_ids:
            continue
        new_rows.append([
            item.get("date", ""),
            item.get("title", "")[:500],
            item.get("summary", "")[:1000],
            item.get("sections_str", ""),
            item.get("url", ""),
            item.get("source_type", ""),
            item.get("unique_id", ""),
            item.get("scraped_at", datetime.utcnow().isoformat()),
        ])

    if not new_rows:
        logger.info(f"No new rows to append to '{tab_name}'")
        return 0

    for attempt in range(1, 4):
        try:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            logger.info(f"Appended {len(new_rows)} rows to tab '{tab_name}'")
            return len(new_rows)
        except Exception as e:
            logger.warning(f"Batch append attempt {attempt} failed: {e}")
            if attempt < 3:
                time.sleep(5)

    # Fallback: row-by-row
    success_count = 0
    for row in new_rows:
        try:
            ws.append_row(row, value_input_option="USER_ENTERED")
            success_count += 1
            time.sleep(0.5)  # rate limit
        except Exception as e:
            logger.error(f"Row-by-row fallback failed: {e}")

    return success_count


def ensure_all_tabs():
    """Ensure all required tabs exist with correct headers."""
    if not _init_client():
        return
    for key, cfg in SOURCES.items():
        _get_or_create_worksheet(cfg["sheet_tab"])
