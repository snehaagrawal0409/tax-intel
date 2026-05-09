"""
main.py
Main orchestrator for the Tax Intelligence System.

Pipeline per source:
  1. Scrape listing page → list of items
  2. Deduplicate (skip already seen)
  3. For each new item:
     a. Fetch full content (HTML/PDF)
     b. Extract clean text
     c. Summarize
     d. Detect IT sections
  4. Send to Telegram
  5. Write to Google Sheets
  6. Mark as seen
"""

import sys
import os
import time
from datetime import datetime, timezone
from typing import Dict, List

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import SOURCES
from src.logger import get_logger
from src.state_manager import is_seen, mark_seen, restore_from_json_if_empty
from src.scrapers import scrape_notifications, scrape_circulars, scrape_caselaws
from src.content_extractor import extract_content_from_url, simple_summarize
from src.section_analyzer import detect_sections, sections_display
from src.telegram_sender import send_item, send_error_alert
from src.sheets_writer import append_item, ensure_all_tabs

logger = get_logger("main")


# ─── Process a single item ────────────────────────────────────────────────────

def process_item(item: Dict, tab_name: str) -> bool:
    """
    Fully process one scraped item:
    extract content → summarize → detect sections → send → store.
    Returns True if successfully processed.
    """
    uid = item.get("unique_id", "")
    title = item.get("title", "")
    url = item.get("url", "")
    source_type = item.get("source_type", "")

    logger.info(f"Processing [{source_type}] {title[:70]}")

    # ── Content extraction ─────────────────────────────────────────────────
    content = ""
    content_type = "unknown"
    try:
        content, content_type = extract_content_from_url(url)
        logger.debug(f"Extracted {len(content)} chars ({content_type}) from {url}")
    except Exception as e:
        logger.warning(f"Content extraction failed for {url}: {e}")
        content = title  # fallback: use title as content

    if not content or len(content.strip()) < 20:
        content = title
        logger.warning(f"Empty content, using title as fallback for {uid}")

    # ── Summarize ──────────────────────────────────────────────────────────
    try:
        summary = simple_summarize(content)
    except Exception as e:
        logger.warning(f"Summarization failed: {e}")
        summary = content[:300] + "…"

    # ── Detect sections ────────────────────────────────────────────────────
    # Detect from both title and content for better coverage
    detection_text = f"{title}\n{content}"
    try:
        sections = detect_sections(detection_text)
    except Exception as e:
        logger.warning(f"Section detection failed: {e}")
        sections = []

    # ── Enrich item ────────────────────────────────────────────────────────
    scraped_at = datetime.now(timezone.utc).isoformat()
    enriched = {
        **item,
        "content": content,
        "content_type": content_type,
        "summary": summary,
        "sections": sections,
        "sections_str": sections_display(sections),
        "scraped_at": scraped_at,
    }

    # ── Send to Telegram ───────────────────────────────────────────────────
    tg_ok = False
    try:
        tg_ok = send_item(enriched)
        if tg_ok:
            logger.info(f"✅ Telegram sent: {title[:60]}")
        else:
            logger.warning(f"⚠️ Telegram send failed: {title[:60]}")
    except Exception as e:
        logger.error(f"Telegram exception for {uid}: {e}")

    # ── Write to Google Sheets ─────────────────────────────────────────────
    sheet_ok = False
    try:
        sheet_ok = append_item(enriched, tab_name)
        if sheet_ok:
            logger.info(f"✅ Sheet written: {title[:60]}")
        else:
            logger.warning(f"⚠️ Sheet write failed: {title[:60]}")
    except Exception as e:
        logger.error(f"Sheet exception for {uid}: {e}")

    # ── Mark as seen (even if downstream failed, to avoid re-scraping) ─────
    mark_seen(uid, source_type, title)

    return tg_ok or sheet_ok  # success if at least one output worked


# ─── Process a source ─────────────────────────────────────────────────────────

def process_source(source_key: str, scraper_fn) -> Dict:
    """
    Run scraper, filter new items, process each one.
    Returns stats dict.
    """
    cfg = SOURCES[source_key]
    tab_name = cfg["sheet_tab"]
    source_type = cfg["type"]

    logger.info(f"\n{'═'*50}")
    logger.info(f"🔍 Processing source: {source_key.upper()}")
    logger.info(f"{'═'*50}")

    stats = {
        "source": source_key,
        "scraped": 0,
        "new": 0,
        "processed": 0,
        "errors": 0,
    }

    # Scrape
    try:
        items = scraper_fn()
        stats["scraped"] = len(items)
        logger.info(f"Scraped {len(items)} items from {source_key}")
    except Exception as e:
        logger.error(f"Scraper crashed for {source_key}: {e}", exc_info=True)
        send_error_alert(f"Scraper crashed for {source_key}: {e}")
        return stats

    if not items:
        logger.warning(f"Zero items scraped from {source_key} — check source or scraping logic")

    # Filter new items
    new_items = [item for item in items if not is_seen(item.get("unique_id", ""))]
    stats["new"] = len(new_items)
    logger.info(f"New items (not yet processed): {len(new_items)}/{len(items)}")

    if not new_items:
        logger.info(f"No new items for {source_key}")
        return stats

    # Process each new item
    for item in new_items:
        try:
            ok = process_item(item, tab_name)
            if ok:
                stats["processed"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            logger.error(f"process_item crashed for {item.get('unique_id')}: {e}", exc_info=True)
            stats["errors"] += 1
            # Still mark as seen to avoid infinite retry loops on broken items
            mark_seen(item.get("unique_id", ""), source_type, item.get("title", ""))

        # Small delay between items to be polite to servers
        time.sleep(1)

    return stats


# ─── Main entry point ─────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("🚀 Tax Intelligence System — Starting Run")
    logger.info(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    # Restore dedup state from JSON backup on fresh CI environments
    restore_from_json_if_empty()

    # Ensure Google Sheets tabs exist
    try:
        ensure_all_tabs()
    except Exception as e:
        logger.warning(f"Could not ensure sheet tabs: {e}")

    all_stats = []

    # Source → scraper function mapping
    sources = [
        ("notifications", scrape_notifications),
        ("circulars",     scrape_circulars),
        ("caselaws",      scrape_caselaws),
    ]

    for source_key, scraper_fn in sources:
        try:
            stats = process_source(source_key, scraper_fn)
            all_stats.append(stats)
        except Exception as e:
            logger.error(f"Fatal error processing {source_key}: {e}", exc_info=True)
            all_stats.append({"source": source_key, "error": str(e)})

    # ── Summary ────────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("📊 RUN SUMMARY")
    logger.info("=" * 60)
    total_new = 0
    total_processed = 0
    for s in all_stats:
        logger.info(
            f"  {s.get('source','?').upper():15s} | "
            f"scraped={s.get('scraped',0):3d} | "
            f"new={s.get('new',0):3d} | "
            f"processed={s.get('processed',0):3d} | "
            f"errors={s.get('errors',0):3d}"
        )
        total_new += s.get("new", 0)
        total_processed += s.get("processed", 0)

    logger.info(f"\n  TOTAL: {total_new} new items found, {total_processed} successfully processed")
    logger.info("=" * 60)
    logger.info("✅ Run complete\n")


if __name__ == "__main__":
    main()
