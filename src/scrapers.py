"""
src/scrapers.py
Source-specific scrapers for:
  1. Income Tax Notifications (incometaxindia.gov.in)
  2. Income Tax Circulars (incometaxindia.gov.in)
  3. ITAT Case Laws (itatonline.org)

Each scraper returns a list of dicts with fields:
  title, url, date, source_type

Full content extraction is done separately by the orchestrator.
"""

import hashlib
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import (
    SOURCES, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    USER_AGENT, MAX_ITEMS_PER_RUN
)
from src.logger import get_logger

logger = get_logger("scrapers")

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})


# ─── HTTP helper ──────────────────────────────────────────────────────────────

def _fetch(url: str, retries: int = MAX_RETRIES) -> Optional[BeautifulSoup]:
    for attempt in range(1, retries + 1):
        try:
            resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt}/{retries} for {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    logger.error(f"All fetch attempts failed: {url}")
    return None


def _fetch_fallback(urls: List[str]) -> Optional[BeautifulSoup]:
    for url in urls:
        soup = _fetch(url)
        if soup:
            return soup
    return None


# ─── Unique ID generation ─────────────────────────────────────────────────────

def make_unique_id(source_type: str, url: str, title: str) -> str:
    """Stable hash-based ID for deduplication."""
    raw = f"{source_type}|{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ─── Date parsing ─────────────────────────────────────────────────────────────

_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y",
    "%d.%m.%Y",
]

def parse_date(raw: str) -> str:
    """Try to parse a date string. Returns ISO format or original."""
    if not raw:
        return ""
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Try extracting date-like substring
    m = re.search(r"\d{2}[/-]\d{2}[/-]\d{4}", raw)
    if m:
        return parse_date(m.group())
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    if m:
        return m.group()
    return raw  # return as-is if we can't parse


# ─── SCRAPER 1: Income Tax India Notifications ────────────────────────────────

def scrape_notifications() -> List[Dict]:
    """
    Scrape income tax notifications from incometaxindia.gov.in.
    Returns list of {title, url, date, source_type, unique_id}.
    """
    cfg = SOURCES["notifications"]
    logger.info(f"Scraping notifications from {cfg['url']}")

    urls_to_try = [cfg["url"]] + cfg.get("fallback_urls", [])
    soup = _fetch_fallback(urls_to_try)
    if not soup:
        logger.error("Could not fetch notifications page")
        return []

    items = _parse_incometaxindia_listing(soup, cfg["url"], cfg["type"])
    logger.info(f"Found {len(items)} notifications")
    return items[:MAX_ITEMS_PER_RUN]


# ─── SCRAPER 2: Income Tax India Circulars ────────────────────────────────────

def scrape_circulars() -> List[Dict]:
    """
    Scrape income tax circulars from incometaxindia.gov.in.
    """
    cfg = SOURCES["circulars"]
    logger.info(f"Scraping circulars from {cfg['url']}")

    urls_to_try = [cfg["url"]] + cfg.get("fallback_urls", [])
    soup = _fetch_fallback(urls_to_try)
    if not soup:
        logger.error("Could not fetch circulars page")
        return []

    items = _parse_incometaxindia_listing(soup, cfg["url"], cfg["type"])
    logger.info(f"Found {len(items)} circulars")
    return items[:MAX_ITEMS_PER_RUN]


def _parse_incometaxindia_listing(soup: BeautifulSoup, base_url: str, source_type: str) -> List[Dict]:
    """
    Parse listing pages from incometaxindia.gov.in.
    Handles both table-based and list-based layouts robustly.
    """
    items = []
    base = "https://www.incometaxindia.gov.in"

    # Strategy 1: Table rows with links
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        link_tag = row.find("a", href=True)
        if not link_tag:
            continue

        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        # Filter navigation links
        if any(kw in href.lower() for kw in ["javascript:", "mailto:", "#"]):
            continue
        if any(kw in title.lower() for kw in ["home", "sitemap", "contact", "feedback", "login"]):
            continue

        url = urljoin(base, href)

        # Try to find date in cells
        date_str = ""
        for cell in cells:
            text = cell.get_text(strip=True)
            if re.search(r"\d{2}[/-]\d{2}[/-]\d{4}", text) or re.search(r"\d{4}-\d{2}-\d{2}", text):
                date_str = parse_date(text)
                break

        uid = make_unique_id(source_type, url, title)
        items.append({
            "title": title,
            "url": url,
            "date": date_str,
            "source_type": source_type,
            "unique_id": uid,
        })

    if items:
        return items

    # Strategy 2: Direct <a> tags with PDF or doc-like hrefs
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        title = a.get_text(strip=True)

        if not title or len(title) < 5:
            continue
        if any(kw in href.lower() for kw in ["javascript:", "mailto:", "#", "facebook", "twitter"]):
            continue
        if not any(ext in href.lower() for ext in [".pdf", ".htm", ".html", ".asp", "/notifications", "/circulars"]):
            continue
        if any(kw in title.lower() for kw in ["home", "sitemap", "contact", "next", "previous", "back"]):
            continue

        url = urljoin(base, href)
        uid = make_unique_id(source_type, url, title)
        items.append({
            "title": title,
            "url": url,
            "date": "",
            "source_type": source_type,
            "unique_id": uid,
        })

    return items


# ─── SCRAPER 3: ITAT Case Laws ────────────────────────────────────────────────

def scrape_caselaws() -> List[Dict]:
    """
    Scrape ITAT case law digests from itatonline.org.
    """
    cfg = SOURCES["caselaws"]
    logger.info(f"Scraping case laws from {cfg['url']}")

    urls_to_try = [cfg["url"]] + cfg.get("fallback_urls", [])
    soup = _fetch_fallback(urls_to_try)
    if not soup:
        logger.error("Could not fetch case laws page")
        return []

    items = _parse_itatonline(soup, cfg["url"], cfg["type"])

    # Also try paginated pages (page 2 & 3) for better coverage
    for page_num in [2, 3]:
        page_url = f"{cfg['url']}page/{page_num}/"
        page_soup = _fetch(page_url)
        if page_soup:
            page_items = _parse_itatonline(page_soup, page_url, cfg["type"])
            items.extend(page_items)
            logger.debug(f"Page {page_num}: {len(page_items)} additional items")

    # Deduplicate by unique_id within this batch
    seen_ids = set()
    deduped = []
    for item in items:
        if item["unique_id"] not in seen_ids:
            seen_ids.add(item["unique_id"])
            deduped.append(item)

    logger.info(f"Found {len(deduped)} case laws")
    return deduped[:MAX_ITEMS_PER_RUN]


def _parse_itatonline(soup: BeautifulSoup, base_url: str, source_type: str) -> List[Dict]:
    """Parse itatonline.org/digest listing page."""
    items = []
    base = "https://itatonline.org"

    # itatonline uses WordPress-style article listings
    # Strategy 1: article tags
    articles = soup.find_all("article")
    for art in articles:
        link_tag = art.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title_tag = art.find(["h1", "h2", "h3", "h4"])
        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

        if not title or len(title) < 5:
            continue

        # Date
        date_str = ""
        date_tag = art.find("time") or art.find(attrs={"class": re.compile(r"date|time|posted", re.I)})
        if date_tag:
            date_str = parse_date(date_tag.get("datetime", "") or date_tag.get_text(strip=True))

        url = urljoin(base, href)
        uid = make_unique_id(source_type, url, title)
        items.append({
            "title": title,
            "url": url,
            "date": date_str,
            "source_type": source_type,
            "unique_id": uid,
        })

    if items:
        return items

    # Strategy 2: h2/h3 with links (common WordPress theme pattern)
    for heading in soup.find_all(["h2", "h3"]):
        link_tag = heading.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(strip=True)

        if not title or len(title) < 5:
            continue
        if any(kw in title.lower() for kw in ["home", "category", "tag", "login", "register"]):
            continue

        url = urljoin(base, href)
        uid = make_unique_id(source_type, url, title)
        items.append({
            "title": title,
            "url": url,
            "date": "",
            "source_type": source_type,
            "unique_id": uid,
        })

    return items
