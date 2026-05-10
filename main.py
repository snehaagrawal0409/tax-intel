"""
main.py — Tax Intelligence System Orchestrator
"""

import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import SOURCES
from src.logger import get_logger
from src.state_manager import is_seen, mark_seen, restore_from_json_if_empty
from src.scrapers import scrape_notifications, scrape_circulars, scrape_caselaws
from src.content_extractor import fetch_content, summarize
from src.section_analyzer import detect_sections, sections_display
from src.telegram_sender import send_item, send_error_alert
from src.sheets_writer import append_item, ensure_all_tabs

logger = get_logger("main")


def _log_env_check():
    """Log which env vars are set (not values) to help debug secrets issues."""
    vars_to_check = [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_NOTIF",
        "TELEGRAM_CHANNEL_CIRCULAR", "TELEGRAM_CHANNEL_CASELAW",
        "TELEGRAM_CHANNEL_IMPORTANT", "GOOGLE_SHEET_ID",
        "GOOGLE_SHEETS_CREDENTIALS",
    ]
    logger.info("=== ENV VAR CHECK ===")
    for v in vars_to_check:
        val = os.environ.get(v, "")
        if val:
            # Show first 6 chars only for security
            preview = val[:6] + "..." if len(val) > 6 else val
            logger.info(f"  {v}: SET ({preview})")
        else:
            logger.warning(f"  {v}: *** NOT SET ***")
    logger.info("====================")


def process_item(item: dict, tab_name: str) -> bool:
    uid        = item.get("unique_id", "")
    title      = item.get("title", "")
    url        = item.get("url", "")
    source_type = item.get("source_type", "")

    logger.info(f"  Processing: {title[:70]}")

    # Content extraction
    content, ctype = "", "none"
    try:
        content, ctype = fetch_content(url)
        logger.debug(f"  Content: {len(content)} chars ({ctype})")
    except Exception as e:
        logger.warning(f"  Content extraction error: {e}")

    if not content or len(content.strip()) < 30:
        content = title
        logger.warning(f"  Using title as content fallback")

    # Summarize
    try:
        summary = summarize(content)
    except Exception as e:
        logger.warning(f"  Summarize error: {e}")
        summary = content[:400] + "…"

    # Detect sections — from title + content combined
    try:
        sections = detect_sections(f"{title}\n{content}")
    except Exception as e:
        logger.warning(f"  Section detect error: {e}")
        sections = []

    enriched = {
        **item,
        "summary":      summary,
        "sections":     sections,
        "sections_str": sections_display(sections),
        "scraped_at":   datetime.now(timezone.utc).isoformat(),
    }

    # Send Telegram
    tg_ok = False
    try:
        tg_ok = send_item(enriched)
        logger.info(f"  Telegram: {'✅ sent' if tg_ok else '❌ failed'}")
    except Exception as e:
        logger.error(f"  Telegram exception: {e}")

    # Write Sheet
    sheet_ok = False
    try:
        sheet_ok = append_item(enriched, tab_name)
        logger.info(f"  Sheet: {'✅ written' if sheet_ok else '❌ failed'}")
    except Exception as e:
        logger.error(f"  Sheet exception: {e}")

    # Always mark seen to avoid infinite retries on broken items
    mark_seen(uid, source_type, title)

    return tg_ok or sheet_ok


def process_source(key: str, scraper_fn) -> dict:
    cfg = SOURCES[key]
    tab = cfg["sheet_tab"]

    logger.info(f"\n{'─'*50}")
    logger.info(f"SOURCE: {key.upper()}")
    logger.info(f"{'─'*50}")

    stats = {"source": key, "scraped": 0, "new": 0, "processed": 0, "errors": 0}

    try:
        items = scraper_fn()
        stats["scraped"] = len(items)
    except Exception as e:
        logger.error(f"Scraper crashed for {key}: {e}", exc_info=True)
        send_error_alert(f"Scraper crashed for {key}: {e}")
        return stats

    if not items:
        logger.warning(f"Zero items scraped from {key}")
        return stats

    new_items = [i for i in items if not is_seen(i.get("unique_id", ""))]
    stats["new"] = len(new_items)
    logger.info(f"New items: {len(new_items)} / {len(items)} total")

    for item in new_items:
        try:
            ok = process_item(item, tab)
            if ok:
                stats["processed"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            logger.error(f"process_item crashed: {e}", exc_info=True)
            stats["errors"] += 1
            mark_seen(item.get("unique_id", ""), cfg["type"], item.get("title", ""))
        time.sleep(1)

    return stats


def main():
    logger.info("=" * 60)
    logger.info("TAX INTELLIGENCE SYSTEM — START")
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    _log_env_check()
    restore_from_json_if_empty()

    try:
        ensure_all_tabs()
    except Exception as e:
        logger.warning(f"Sheet tab setup warning: {e}")

    sources = [
        ("notifications", scrape_notifications),
        ("circulars",     scrape_circulars),
        ("caselaws",      scrape_caselaws),
    ]

    all_stats = []
    for key, fn in sources:
        try:
            stats = process_source(key, fn)
            all_stats.append(stats)
        except Exception as e:
            logger.error(f"Fatal error for {key}: {e}", exc_info=True)

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for s in all_stats:
        logger.info(
            f"  {s.get('source','?').upper():15s} | "
            f"scraped={s.get('scraped',0):3d} | "
            f"new={s.get('new',0):3d} | "
            f"processed={s.get('processed',0):3d} | "
            f"errors={s.get('errors',0):3d}"
        )
    logger.info("=" * 60)
    logger.info("DONE\n")


if __name__ == "__main__":
    main()
