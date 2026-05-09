"""
config/settings.py
Central configuration for the Tax Intelligence System.
All environment variables and constants are defined here.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict

# ─── Environment Variables ────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_NOTIF    = os.getenv("TELEGRAM_CHANNEL_NOTIF", "")      # e.g. @TaxNotifications
TELEGRAM_CHANNEL_CIRCULAR = os.getenv("TELEGRAM_CHANNEL_CIRCULAR", "")   # e.g. @TaxCirculars
TELEGRAM_CHANNEL_CASELAW  = os.getenv("TELEGRAM_CHANNEL_CASELAW", "")    # e.g. @TaxCaseLaws
TELEGRAM_CHANNEL_IMPORTANT= os.getenv("TELEGRAM_CHANNEL_IMPORTANT", "")  # e.g. @TaxImportant

GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "")   # JSON string of service account
GOOGLE_SHEET_ID           = os.getenv("GOOGLE_SHEET_ID", "")             # Sheet ID from URL

# ─── Source URLs ──────────────────────────────────────────────────────────────
SOURCES = {
    "notifications": {
        "url": "https://www.incometaxindia.gov.in/notifications",
        "fallback_urls": [
            "https://www.incometaxindia.gov.in/Pages/notifications.aspx",
        ],
        "type": "Notification",
        "sheet_tab": "Notifications",
        "telegram_channel_env": "TELEGRAM_CHANNEL_NOTIF",
    },
    "circulars": {
        "url": "https://www.incometaxindia.gov.in/circulars",
        "fallback_urls": [
            "https://www.incometaxindia.gov.in/Pages/circulars.aspx",
        ],
        "type": "Circular",
        "sheet_tab": "Circulars",
        "telegram_channel_env": "TELEGRAM_CHANNEL_CIRCULAR",
    },
    "caselaws": {
        "url": "https://itatonline.org/digest/all-judgements/",
        "fallback_urls": [
            "https://itatonline.org/digest/",
        ],
        "type": "Case Law",
        "sheet_tab": "Case Laws",
        "telegram_channel_env": "TELEGRAM_CHANNEL_CASELAW",
    },
}

# ─── Important Sections ───────────────────────────────────────────────────────
# Items containing these sections will ALSO be sent to TELEGRAM_CHANNEL_IMPORTANT
IMPORTANT_SECTIONS: List[str] = [
    "80C", "80D", "80G", "80GG", "80U",
    "194J", "194C", "194H", "194I", "194A", "194B", "194N",
    "148", "148A", "147",
    "37(1)", "37",
    "139", "139(1)", "139(4)", "139(5)",
    "271AAC", "271AAB", "271(1)(c)", "271B",
    "234A", "234B", "234C",
    "10(10D)", "10(23C)", "10(38)",
    "56(2)", "68", "69", "69A",
    "92", "92A", "92B", "92C",
    "245",
]

# ─── Scraping Config ──────────────────────────────────────────────────────────
REQUEST_TIMEOUT     = 30          # seconds
MAX_RETRIES         = 3
RETRY_DELAY         = 5           # seconds between retries
MAX_ITEMS_PER_RUN   = 50          # max new items to process per source per run
USER_AGENT          = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─── State / Dedup ────────────────────────────────────────────────────────────
STATE_DB_PATH       = "state/seen_items.db"     # SQLite database
STATE_JSON_BACKUP   = "state/seen_items.json"   # JSON backup

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE            = "logs/tax_intel.log"

# ─── Google Sheets columns ───────────────────────────────────────────────────
SHEET_COLUMNS = ["Date", "Heading", "Summary", "Sections", "Link", "Source Type", "Unique ID", "Scraped Timestamp"]

# ─── Summarizer ──────────────────────────────────────────────────────────────
SUMMARY_MAX_CHARS   = 600         # max chars of extracted text fed to summarizer
SUMMARY_MAX_LINES   = 3

# ─── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_MAX_LEN    = 4096
TELEGRAM_RETRY      = 3
TELEGRAM_RETRY_DELAY= 4
