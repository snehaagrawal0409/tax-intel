"""
src/sheets_writer.py — Append items to Google Sheets using gspread.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

from config.settings import GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS, SOURCES
from src.logger import get_logger

logger = get_logger("sheets_writer")

_gc    = None   # gspread client (lazy init)
_sheet = None   # Spreadsheet object


# ---------------------------------------------------------------------------
# Auth / init
# ---------------------------------------------------------------------------

def _get_client():
    global _gc
    if _gc:
        return _gc

    if not GOOGLE_SHEETS_CREDENTIALS:
        logger.warning("GOOGLE_SHEETS_CREDENTIALS not set")
        return None

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
        scopes     = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        _gc   = gspread.authorize(creds)
        return _gc
    except Exception as e:
        logger.error(f"Sheets auth error: {e}")
        return None


def _get_sheet():
    global _sheet
    if _sheet:
        return _sheet

    gc = _get_client()
    if not gc:
        return None

    if not GOOGLE_SHEET_ID:
        logger.warning("GOOGLE_SHEET_ID not set")
        return None

    try:
        _sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        return _sheet
    except Exception as e:
        logger.error(f"Open sheet error: {e}")
        return None


# ---------------------------------------------------------------------------
# Tab management
# ---------------------------------------------------------------------------

HEADERS = [
    "Date", "Heading", "Summary", "Sections",
    "Link", "Source Type", "Unique ID", "Scraped Timestamp",
]


def ensure_all_tabs() -> None:
    """Create all required tabs with header rows if they don't exist."""
    sh = _get_sheet()
    if not sh:
        return

    existing = {ws.title for ws in sh.worksheets()}
    for cfg in SOURCES.values():
        tab = cfg["sheet_tab"]
        if tab not in existing:
            try:
                ws = sh.add_worksheet(title=tab, rows=1000, cols=len(HEADERS))
                ws.append_row(HEADERS, value_input_option="RAW")
                logger.info(f"Created sheet tab: {tab}")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Could not create tab {tab}: {e}")
        else:
            # Ensure header exists
            try:
                ws = sh.worksheet(tab)
                first_row = ws.row_values(1)
                if not first_row or first_row[0] != "Date":
                    ws.insert_row(HEADERS, index=1, value_input_option="RAW")
            except Exception as e:
                logger.warning(f"Header check failed for {tab}: {e}")


# ---------------------------------------------------------------------------
# Write item
# ---------------------------------------------------------------------------

def append_item(item: dict, tab_name: str, retries: int = 3) -> bool:
    sh = _get_sheet()
    if not sh:
        return False

    row = [
        item.get("date", ""),
        item.get("title", "")[:500],
        item.get("summary", "")[:1000],
        item.get("sections_str", ""),
        item.get("url", ""),
        item.get("source_type", ""),
        item.get("unique_id", ""),
        item.get("scraped_at", datetime.now(timezone.utc).isoformat()),
    ]

    for attempt in range(1, retries + 1):
        try:
            ws = sh.worksheet(tab_name)
            ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            logger.warning(f"Sheet write attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(3 * attempt)

    return False
