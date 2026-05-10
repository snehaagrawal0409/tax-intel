"""
src/telegram_sender.py — Send formatted messages to Telegram channels.
"""

import time
from typing import Optional

import requests

from config.settings import (
    IMPORTANT_SECTIONS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_CIRCULAR,
    TELEGRAM_CHANNEL_CASELAW,
    TELEGRAM_CHANNEL_IMPORTANT,
    TELEGRAM_CHANNEL_NOTIF,
)
from src.logger import get_logger

logger = get_logger("telegram_sender")

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


# ---------------------------------------------------------------------------
# Internal send primitive
# ---------------------------------------------------------------------------

def _send(chat_id: str, text: str, retries: int = 3) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping send")
        return False
    if not chat_id:
        logger.warning("chat_id empty — skipping send")
        return False

    url     = _API_BASE.format(token=TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id":                  chat_id,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if data.get("ok"):
                return True
            # Telegram error
            err = data.get("description", "unknown error")
            logger.warning(f"Telegram API error (attempt {attempt}): {err}")
            if "Too Many Requests" in err:
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                time.sleep(retry_after)
            else:
                time.sleep(2)
        except Exception as e:
            logger.warning(f"Telegram send exception (attempt {attempt}): {e}")
            time.sleep(3 * attempt)

    return False


# ---------------------------------------------------------------------------
# Message formatter
# ---------------------------------------------------------------------------

def _format_message(item: dict) -> str:
    source_type  = item.get("source_type", "").lower()
    title        = item.get("title", "")
    url          = item.get("url", "")
    date         = item.get("date", "")
    summary      = item.get("summary", "")
    sections_str = item.get("sections_str", "")
    sections     = item.get("sections", [])

    # Header emoji + label
    type_labels = {
        "notification": ("📋", "Notification"),
        "circular":     ("📢", "Circular"),
        "caselaw":      ("⚖️",  "ITAT Case Law"),
    }
    emoji, label = type_labels.get(source_type, ("📄", source_type.title()))

    # Important sections badge
    important_badge = ""
    if any(s in IMPORTANT_SECTIONS for s in sections):
        important_badge = " 🔥 <b>IMPORTANT SECTIONS</b>"

    lines = [
        f"{emoji} <b>{label}</b>{important_badge}",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if date:
        lines.append(f"📅 <b>Date:</b> {date}")
    lines.append(f"📌 <b>Title:</b> {_escape(title)}")
    if sections_str:
        lines.append(f"🏷️ <b>Sections:</b> {_escape(sections_str)}")
    lines.append("━━━━━━━━━━━━━━━━━━")

    if summary:
        lines.append(f"📝 <b>Summary:</b>")
        # Telegram message limit: 4096 chars. Reserve space for the rest.
        max_summary = 3000 - sum(len(l) for l in lines)
        lines.append(_escape(summary[:max(200, max_summary)]))
        lines.append("━━━━━━━━━━━━━━━━━━")

    if url:
        lines.append(f'🔗 <a href="{url}">View Source</a>')

    return "\n".join(lines)


def _escape(text: str) -> str:
    """Minimal HTML escape for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_item(item: dict) -> bool:
    source_type  = item.get("source_type", "")
    sections     = item.get("sections", [])

    channel_map = {
        "notification": TELEGRAM_CHANNEL_NOTIF,
        "circular":     TELEGRAM_CHANNEL_CIRCULAR,
        "caselaw":      TELEGRAM_CHANNEL_CASELAW,
    }
    primary_channel = channel_map.get(source_type, "")

    if not primary_channel:
        logger.warning(f"No channel configured for source_type={source_type}")
        return False

    message = _format_message(item)

    # Trim if over 4096 limit
    if len(message) > 4096:
        message = message[:4090] + "…"

    ok = _send(primary_channel, message)

    # Also send to IMPORTANT channel if relevant sections found
    if TELEGRAM_CHANNEL_IMPORTANT and any(s in IMPORTANT_SECTIONS for s in sections):
        _send(TELEGRAM_CHANNEL_IMPORTANT, message)
        time.sleep(0.5)

    return ok


def send_error_alert(error_text: str) -> None:
    if not TELEGRAM_CHANNEL_IMPORTANT:
        return
    msg = f"🚨 <b>Tax Intel Error</b>\n\n<code>{_escape(str(error_text)[:500])}</code>"
    _send(TELEGRAM_CHANNEL_IMPORTANT, msg)
