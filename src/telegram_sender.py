"""
src/telegram_sender.py
Reads ALL credentials from environment at call-time.
"""

import os
import time
from typing import Dict, List

import requests

from src.section_analyzer import is_important, sections_display
from src.logger import get_logger

logger = get_logger("telegram_sender")

_TYPE_EMOJI = {"Notification": "📋", "Circular": "🔵", "Case Law": "⚖️"}
MAX_LEN     = 4096
RETRIES     = 3
RETRY_DELAY = 4


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")

def _channel(source_type: str) -> str:
    return {
        "Notification": os.environ.get("TELEGRAM_CHANNEL_NOTIF", ""),
        "Circular":     os.environ.get("TELEGRAM_CHANNEL_CIRCULAR", ""),
        "Case Law":     os.environ.get("TELEGRAM_CHANNEL_CASELAW", ""),
    }.get(source_type, "")

def _important_ch() -> str:
    return os.environ.get("TELEGRAM_CHANNEL_IMPORTANT", "")


def _build_msg(item: Dict) -> str:
    emoji    = _TYPE_EMOJI.get(item.get("source_type", ""), "📄")
    sections = item.get("sections", [])
    imp_flag = " 🔥 <b>IMPORTANT</b>" if is_important(sections) else ""
    summary  = (item.get("summary") or "No summary available.")[:600]
    title    = (item.get("title") or "N/A")[:300]
    date     = item.get("date") or "N/A"
    url      = item.get("url", "")
    stype    = item.get("source_type", "Update")
    secs     = sections_display(sections)

    return (
        f"{emoji} <b>{stype}</b>{imp_flag}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Date:</b> {date}\n"
        f"📌 <b>Title:</b> {title}\n"
        f"🏷 <b>Sections:</b> {secs}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Summary:</b>\n{summary}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href=\"{url}\">View Source</a>"
    )


def _split(text: str) -> List[str]:
    if len(text) <= MAX_LEN:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, MAX_LEN)
        if cut == -1:
            cut = MAX_LEN
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    return chunks


def _send(channel: str, text: str) -> bool:
    token = _token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False
    if not channel:
        logger.warning("No Telegram channel set — skipping")
        return False

    api = f"https://api.telegram.org/bot{token}/sendMessage"
    for i, chunk in enumerate(_split(text)):
        sent = False
        for attempt in range(1, RETRIES + 1):
            try:
                r = requests.post(
                    api,
                    json={"chat_id": channel, "text": chunk,
                          "parse_mode": "HTML", "disable_web_page_preview": True},
                    timeout=15,
                )
                if r.ok:
                    sent = True
                    break
                # Log exact Telegram error
                err = r.json().get("description", r.text[:300])
                logger.warning(f"Telegram error (attempt {attempt}): {r.status_code} — {err}")
                # If bad channel ID, no point retrying
                if r.status_code == 400 and "chat not found" in err.lower():
                    logger.error(f"CHANNEL NOT FOUND: '{channel}' — check TELEGRAM_CHANNEL_* secret")
                    return False
            except Exception as e:
                logger.warning(f"Telegram send exception attempt {attempt}: {e}")
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)

        if not sent:
            logger.error(f"Failed sending chunk {i+1} to {channel}")
            return False
        if i > 0:
            time.sleep(0.5)

    return True


def send_item(item: Dict) -> bool:
    ch = _channel(item.get("source_type", ""))
    if not ch:
        logger.error(
            f"No channel env var set for source_type='{item.get('source_type')}'. "
            f"Check TELEGRAM_CHANNEL_NOTIF / TELEGRAM_CHANNEL_CIRCULAR / TELEGRAM_CHANNEL_CASELAW secrets."
        )
        return False

    msg = _build_msg(item)
    ok  = _send(ch, msg)

    # Also send to important channel if relevant sections
    imp = _important_ch()
    if is_important(item.get("sections", [])) and imp and imp != ch:
        _send(imp, msg)

    return ok


def send_error_alert(message: str):
    ch = _important_ch() or os.environ.get("TELEGRAM_CHANNEL_NOTIF", "")
    if ch:
        _send(ch, f"⚠️ <b>Tax Intel Error</b>\n\n{message[:400]}")
