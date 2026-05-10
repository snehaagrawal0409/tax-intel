"""
src/telegram_sender.py
Fixed: reads ALL env vars at call-time (not import-time).
This is critical for GitHub Actions where secrets are injected at runtime.
"""

import os
import time
from typing import Dict, List, Optional

import requests

from src.section_analyzer import is_important, sections_display
from src.logger import get_logger

logger = get_logger("telegram_sender")

_TYPE_EMOJI = {
    "Notification": "📋",
    "Circular":     "🔵",
    "Case Law":     "⚖️",
}

TELEGRAM_MAX_LEN    = 4096
TELEGRAM_RETRY      = 3
TELEGRAM_RETRY_DELAY = 4


def _token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")

def _channel(source_type: str) -> str:
    mapping = {
        "Notification": os.environ.get("TELEGRAM_CHANNEL_NOTIF", ""),
        "Circular":     os.environ.get("TELEGRAM_CHANNEL_CIRCULAR", ""),
        "Case Law":     os.environ.get("TELEGRAM_CHANNEL_CASELAW", ""),
    }
    return mapping.get(source_type, "")

def _important_channel():
    return os.environ.get("TELEGRAM_CHANNEL_IMPORTANT", "")


def _build_message(item: Dict) -> str:
    emoji = _TYPE_EMOJI.get(item.get("source_type", ""), "📄")
    sections = item.get("sections", [])
    imp_flag = " 🔥 <b>IMPORTANT SECTIONS</b>" if is_important(sections) else ""
    sections_str = sections_display(sections)
    summary = (item.get("summary") or "No summary available.")[:800]

    return (
        f"{emoji} <b>{item.get('source_type', 'Update')}</b>{imp_flag}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Date:</b> {item.get('date') or 'N/A'}\n"
        f"📌 <b>Title:</b> {(item.get('title') or 'N/A')[:300]}\n"
        f"🏷️ <b>Sections:</b> {sections_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Summary:</b>\n{summary}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href=\"{item.get('url', '')}\">View Source</a>"
    )


def _split_message(text: str) -> List[str]:
    if len(text) <= TELEGRAM_MAX_LEN:
        return [text]
    chunks = []
    while text:
        if len(text) <= TELEGRAM_MAX_LEN:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, TELEGRAM_MAX_LEN)
        if split_at == -1:
            split_at = TELEGRAM_MAX_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


def _send_to_channel(channel: str, text: str) -> bool:
    token = _token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        return False
    if not channel:
        logger.warning("No Telegram channel configured — skipping")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = _split_message(text)

    for i, chunk in enumerate(chunks):
        sent = False
        for attempt in range(1, TELEGRAM_RETRY + 1):
            try:
                resp = requests.post(
                    api_url,
                    json={
                        "chat_id": channel,
                        "text": chunk,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
                if resp.ok:
                    logger.debug(f"Sent chunk {i+1}/{len(chunks)} to {channel}")
                    sent = True
                    break
                else:
                    err = resp.json().get("description", resp.text[:200])
                    logger.warning(f"Telegram API error attempt {attempt}: {resp.status_code} — {err}")
            except Exception as e:
                logger.warning(f"Telegram send attempt {attempt} exception: {e}")

            if attempt < TELEGRAM_RETRY:
                time.sleep(TELEGRAM_RETRY_DELAY)

        if not sent:
            logger.error(f"Failed to send to {channel} after {TELEGRAM_RETRY} attempts")
            return False

        if len(chunks) > 1:
            time.sleep(0.5)

    return True


def send_item(item: Dict) -> bool:
    source_type = item.get("source_type", "")
    channel = _channel(source_type)

    if not channel:
        logger.warning(f"No channel configured for source_type='{source_type}' — check secrets")
        return False

    msg = _build_message(item)
    primary_ok = _send_to_channel(channel, msg)

    # Also route to IMPORTANT channel if relevant sections found
    sections = item.get("sections", [])
    imp_ch = _important_channel()
    if is_important(sections) and imp_ch and imp_ch != channel:
        logger.info(f"Routing to IMPORTANT channel: {item.get('title', '')[:60]}")
        _send_to_channel(imp_ch, msg)

    return primary_ok


def send_error_alert(message: str):
    target = _important_channel() or os.environ.get("TELEGRAM_CHANNEL_NOTIF", "")
    if target:
        _send_to_channel(target, f"⚠️ <b>Tax Intel Error</b>\n\n{message[:500]}")
