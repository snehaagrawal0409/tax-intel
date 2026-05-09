"""
src/telegram_sender.py
Sends formatted messages to Telegram channels.
Handles message splitting, retries, and routing to important-sections channel.
"""

import time
from typing import Dict, List, Optional

import requests

from config.settings import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_NOTIF, TELEGRAM_CHANNEL_CIRCULAR,
    TELEGRAM_CHANNEL_CASELAW, TELEGRAM_CHANNEL_IMPORTANT,
    TELEGRAM_MAX_LEN, TELEGRAM_RETRY, TELEGRAM_RETRY_DELAY,
    SOURCES,
)
from src.section_analyzer import is_important, sections_display
from src.logger import get_logger

logger = get_logger("telegram_sender")

_CHANNEL_MAP = {
    "Notification": TELEGRAM_CHANNEL_NOTIF,
    "Circular":     TELEGRAM_CHANNEL_CIRCULAR,
    "Case Law":     TELEGRAM_CHANNEL_CASELAW,
}

_TYPE_EMOJI = {
    "Notification": "📋",
    "Circular":     "🔵",
    "Case Law":     "⚖️",
}


def _get_channel(source_type: str) -> str:
    """Get Telegram channel ID/username for a source type."""
    return _CHANNEL_MAP.get(source_type, "")


def _build_message(item: Dict) -> str:
    """
    Build a formatted Telegram message from an item dict.
    Uses HTML parse mode.
    """
    emoji = _TYPE_EMOJI.get(item.get("source_type", ""), "📄")
    sections = item.get("sections", [])
    imp_flag = " 🔥 <b>IMPORTANT SECTIONS</b>" if is_important(sections) else ""
    sections_str = sections_display(sections)

    msg = (
        f"{emoji} <b>{item.get('source_type', 'Update')}</b>{imp_flag}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Date:</b> {item.get('date', 'N/A')}\n"
        f"📌 <b>Title:</b> {item.get('title', 'N/A')}\n"
        f"🏷️ <b>Sections:</b> {sections_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Summary:</b>\n{item.get('summary', 'No summary available.')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href=\"{item.get('url', '')}\">View Source</a>"
    )
    return msg


def _split_message(text: str, limit: int = TELEGRAM_MAX_LEN) -> List[str]:
    """Split a long message into chunks within Telegram's character limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Find last newline before limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks


def _send_to_channel(channel: str, text: str) -> bool:
    """
    Send text to a Telegram channel. Returns True on success.
    Retries on failure.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set — cannot send message")
        return False
    if not channel:
        logger.warning("No channel configured — skipping message send")
        return False

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = _split_message(text)

    for chunk_idx, chunk in enumerate(chunks):
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
                    logger.debug(f"Sent chunk {chunk_idx + 1}/{len(chunks)} to {channel}")
                    sent = True
                    break
                else:
                    logger.warning(
                        f"Telegram API error (attempt {attempt}): {resp.status_code} {resp.text[:200]}"
                    )
            except Exception as e:
                logger.warning(f"Telegram send attempt {attempt} failed: {e}")

            if attempt < TELEGRAM_RETRY:
                time.sleep(TELEGRAM_RETRY_DELAY)

        if not sent:
            logger.error(f"Failed to send chunk {chunk_idx + 1} to {channel} after {TELEGRAM_RETRY} attempts")
            return False

        # Rate limit: Telegram allows ~30 messages/second per bot
        if len(chunks) > 1:
            time.sleep(0.5)

    return True


def send_item(item: Dict) -> bool:
    """
    Send an item to its primary channel, and optionally to IMPORTANT channel.
    Returns True if primary channel send succeeded.
    """
    source_type = item.get("source_type", "")
    channel = _get_channel(source_type)

    msg = _build_message(item)
    primary_ok = _send_to_channel(channel, msg)

    # Also send to IMPORTANT channel if applicable
    sections = item.get("sections", [])
    if is_important(sections) and TELEGRAM_CHANNEL_IMPORTANT:
        logger.info(f"Routing to IMPORTANT channel: {item.get('title', '')[:60]}")
        _send_to_channel(TELEGRAM_CHANNEL_IMPORTANT, msg)

    return primary_ok


def send_error_alert(message: str, channel: Optional[str] = None):
    """Send an error/alert message to a configured channel (optional)."""
    target = channel or TELEGRAM_CHANNEL_IMPORTANT or TELEGRAM_CHANNEL_NOTIF
    if target:
        _send_to_channel(target, f"⚠️ <b>Tax Intel System Error</b>\n\n{message[:500]}")
