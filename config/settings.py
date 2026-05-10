"""
config/settings.py
"""
import os

GOOGLE_SHEETS_CREDENTIALS = os.environ.get("GOOGLE_SHEETS_CREDENTIALS", "")
GOOGLE_SHEET_ID           = os.environ.get("GOOGLE_SHEET_ID", "")

SOURCES = {
    "notifications": {
        "url": "https://www.incometaxindia.gov.in/communications/notification/",
        "type": "Notification",
        "sheet_tab": "Notifications",
    },
    "circulars": {
        "url": "https://www.incometaxindia.gov.in/communications/circular/",
        "type": "Circular",
        "sheet_tab": "Circulars",
    },
    "caselaws": {
        "url": "https://itatonline.org/digest/all-judgements/",
        "type": "Case Law",
        "sheet_tab": "Case Laws",
    },
}

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
    "92", "92A", "92B", "92C", "245",
]

REQUEST_TIMEOUT   = 60
MAX_RETRIES       = 2
RETRY_DELAY       = 3
MAX_ITEMS_PER_RUN = 30
STATE_DB_PATH     = "state/seen_items.db"
STATE_JSON_BACKUP = "state/seen_items.json"
LOG_LEVEL         = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE          = "logs/tax_intel.log"
SHEET_COLUMNS     = ["Date","Heading","Summary","Sections","Link","Source Type","Unique ID","Scraped Timestamp"]
