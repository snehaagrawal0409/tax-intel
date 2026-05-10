"""
config/settings.py — All configuration for Tax Intelligence System
"""

import os

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN         = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_NOTIF     = os.environ.get("TELEGRAM_CHANNEL_NOTIF", "")
TELEGRAM_CHANNEL_CIRCULAR  = os.environ.get("TELEGRAM_CHANNEL_CIRCULAR", "")
TELEGRAM_CHANNEL_CASELAW   = os.environ.get("TELEGRAM_CHANNEL_CASELAW", "")
TELEGRAM_CHANNEL_IMPORTANT = os.environ.get("TELEGRAM_CHANNEL_IMPORTANT", "")

# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------
GOOGLE_SHEET_ID          = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")  # full JSON string

# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------
SOURCES = {
    "notifications": {
        "type":      "notification",
        "sheet_tab": "Notifications",
        "urls": [
            "https://www.incometax.gov.in/iec/foportal/help/notifications",
            "https://incometaxindia.gov.in/communications/notification/",
        ],
    },
    "circulars": {
        "type":      "circular",
        "sheet_tab": "Circulars",
        "urls": [
            "https://www.incometax.gov.in/iec/foportal/help/circulars",
            "https://incometaxindia.gov.in/communications/circular/",
        ],
    },
    "caselaws": {
        "type":      "caselaw",
        "sheet_tab": "Case Laws",
        "urls": [
            "https://www.itatonline.org/archives/",
            "https://www.itatonline.org/",
        ],
    },
}

# ---------------------------------------------------------------------------
# Sections that trigger an additional alert to IMPORTANT channel
# ---------------------------------------------------------------------------
IMPORTANT_SECTIONS = [
    "80C", "80D", "80G", "80GG", "80GGA", "80GGC",
    "148", "148A", "147", "144C",
    "194J", "194C", "194H", "194I", "194N", "194Q",
    "271AAC", "271AAB", "271B",
    "10", "10A", "10AA",
    "132", "132A", "133A",
    "12A", "12AA", "12AB",
    "56", "68", "69", "69A", "69B", "69C",
    "263", "264",
    "45", "48", "50C", "54", "54F",
]

# ---------------------------------------------------------------------------
# HTTP settings
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 20  # seconds
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# State / deduplication
# ---------------------------------------------------------------------------
STATE_DIR      = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
DB_PATH        = os.path.join(STATE_DIR, "seen_items.db")
JSON_BACKUP    = os.path.join(STATE_DIR, "seen_items.json")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR        = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_LEVEL      = os.environ.get("LOG_LEVEL", "INFO")
