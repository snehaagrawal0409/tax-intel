"""
config/settings.py
All configuration. Telegram channel IDs are read at call-time in telegram_sender.py
(not here) to ensure GitHub Actions secrets are available.
"""

import os

# ─── Google Sheets ────────────────────────────────────────────────────────────
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")
GOOGLE_SHEET_ID           = os.environ.get("GOOGLE_SHEET_ID", "")

# ─── Sources ──────────────────────────────────────────────────────────────────
SOURCES = {
    "notifications": {
        "url": "https://www.incometaxindia.gov.in/communications/notification/",
        "fallback_urls": [
            "https://www.incometaxindia.gov.in/Pages/communications/notification.aspx",
        ],
        "type": "Notification",
        "sheet_tab": "Notifications",
    },
    "circulars": {
        "url": "https://www.incometaxindia.gov.in/communications/circular/",
        "fallback_urls": [
            "https://www.incometaxindia.gov.in/Pages/communications/circular.aspx",
        ],
        "type": "Circular",
        "sheet_tab": "Circulars",
    },
    "caselaws": {
        "url": "https://itatonline.org/digest/all-judgements/",
        "fallback_urls": [
            "https://itatonline.org/digest/",
        ],
        "type": "Case Law",
        "sheet_tab": "Case Laws",
    },
}

# ─── Important Sections ───────────────────────────────────────────────────────
IMPORTANT_SECTIONS = [
    "80C", "80D", "80G", "80GG", "80U",
    "194J", "194C", "194H", "194I", "194A", "194B", "194N",
    "148", "148A", "147",
    "37", "37(1)",
    "139", "139(1)", "139(4)", "139(5)",
    "271AAC", "271AAB", "271(1)(c)", "271B",
    "234A", "234B", "234C",
    "10(10D)", "10(23C)", "10(38)",
    "56(2)", "68", "69", "69A",
    "92", "92A", "92B", "92C",
    "245",
]

# ─── Scraping ─────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT   = 30
MAX_RETRIES       = 3
RETRY_DELAY       = 5
MAX_ITEMS_PER_RUN = 50
USER_AGENT        = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─── State ────────────────────────────────────────────────────────────────────
STATE_DB_PATH     = "state/seen_items.db"
STATE_JSON_BACKUP = "state/seen_items.json"

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE  = "logs/tax_intel.log"

# ─── Google Sheets columns ───────────────────────────────────────────────────
SHEET_COLUMNS = [
    "Date", "Heading", "Summary", "Sections",
    "Link", "Source Type", "Unique ID", "Scraped Timestamp"
]

# ─── Summarizer ──────────────────────────────────────────────────────────────
SUMMARY_MAX_CHARS = 600
SUMMARY_MAX_LINES = 3
