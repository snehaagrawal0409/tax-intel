"""
src/scrapers.py
Fixed scrapers for all 3 sources.
- Notifications: correct URL + PDF link extraction
- Circulars: correct URL + PDF link extraction
- Case Laws: itatonline.org with fallback
- No cross-contamination between sources
"""

import hashlib
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

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
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
})

_ITI_BASE = "https://www.incometaxindia.gov.in"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch(url, retries=MAX_RETRIES):
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


def _make_uid(source_type, url, title):
    raw = f"{source_type}|{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_DATE_FMTS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y", "%d.%m.%Y",
]

def _parse_date(raw):
    if not raw:
        return ""
    raw = raw.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", raw)
    if m:
        return _parse_date(m.group())
    return raw


def _dedup(items):
    seen, result = set(), []
    for item in items:
        uid = item.get("unique_id", "")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(item)
    return result


def _abs_url(href):
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return _ITI_BASE + href
    return _ITI_BASE + "/" + href


# ─── SCRAPER 1: Notifications ─────────────────────────────────────────────────

def scrape_notifications():
    source_type = "Notification"
    logger.info("Scraping notifications...")

    listing_urls = [
        "https://www.incometaxindia.gov.in/communications/notification/",
        "https://www.incometaxindia.gov.in/Pages/communications/notification.aspx",
    ]

    items = []
    for url in listing_urls:
        soup = _fetch(url)
        if not soup:
            continue
        found = _parse_iti_listing(soup, url, source_type)
        if found:
            logger.info(f"Found {len(found)} notifications from {url}")
            items = found
            break

    if not items:
        logger.warning("Trying taxguru fallback for notifications")
        items = _scrape_taxguru_mirror(
            "https://taxguru.in/income-tax/notifications/", source_type
        )

    items = _dedup(items)
    logger.info(f"Total notifications scraped: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


# ─── SCRAPER 2: Circulars ─────────────────────────────────────────────────────

def scrape_circulars():
    source_type = "Circular"
    logger.info("Scraping circulars...")

    listing_urls = [
        "https://www.incometaxindia.gov.in/communications/circular/",
        "https://www.incometaxindia.gov.in/Pages/communications/circular.aspx",
    ]

    items = []
    for url in listing_urls:
        soup = _fetch(url)
        if not soup:
            continue
        found = _parse_iti_listing(soup, url, source_type)
        if found:
            logger.info(f"Found {len(found)} circulars from {url}")
            items = found
            break

    if not items:
        logger.warning("Trying taxguru fallback for circulars")
        items = _scrape_taxguru_mirror(
            "https://taxguru.in/income-tax/circulars/", source_type
        )

    items = _dedup(items)
    logger.info(f"Total circulars scraped: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


def _parse_iti_listing(soup, page_url, source_type):
    """
    Parse incometaxindia.gov.in listing pages.
    Extracts real document links (PDFs or detail pages), not nav/homepage links.
    """
    items = []

    skip_hrefs = {"/", "#", "", "javascript:void(0)"}
    skip_titles = {
        "home", "sitemap", "contact", "feedback", "login", "logout",
        "back", "next", "previous", "print", "share", "search",
        "screen reader", "skip to", "english", "hindi", "accessibility",
        "about us", "disclaimer", "privacy", "help", "faq", "subscribe",
        "notifications", "circulars", "press releases",
    }

    def is_real_doc(href, title):
        if not href or not title:
            return False
        href_l = href.lower()
        title_l = title.lower().strip()
        if href.strip() in skip_hrefs:
            return False
        if any(bad in href_l for bad in ["javascript:", "mailto:", "facebook", "twitter", "youtube", "instagram"]):
            return False
        if len(title.strip()) < 8:
            return False
        if title_l in skip_titles:
            return False
        if any(title_l.startswith(w) for w in ["home", "contact", "about", "login", "skip"]):
            return False
        # Positive signals
        is_pdf = ".pdf" in href_l
        has_number = bool(re.search(r'\d{1,4}[/\-_]\d{2,4}', title))
        has_keyword = bool(re.search(
            r'(notification|circular|order|instruction|press|guideline|'
            r'amendment|clarif|cbdt|income.?tax|rule\s+\d|section\s*\d)',
            title, re.IGNORECASE
        ))
        in_comms_path = any(x in href_l for x in [
            "/communications/", "notification_", "circular_",
            "/notification/", "/circular/",
        ])
        return is_pdf or has_number or has_keyword or in_comms_path

    # Strategy 1: Table rows
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            link_tag = row.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag.get("href", "").strip()
            title = link_tag.get_text(separator=" ", strip=True)
            if not is_real_doc(href, title):
                continue
            url = _abs_url(href)
            date_str = ""
            for cell in row.find_all(["td", "th"]):
                text = cell.get_text(strip=True)
                m = re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", text)
                if m:
                    date_str = _parse_date(m.group())
                    break
            uid = _make_uid(source_type, url, title)
            items.append({"title": title, "url": url, "date": date_str,
                          "source_type": source_type, "unique_id": uid})

    if items:
        return items

    # Strategy 2: Content area links
    content_area = (
        soup.find("div", id=re.compile(r"content|main|body", re.I)) or
        soup.find("div", class_=re.compile(r"content|main|listing|table", re.I)) or
        soup.find("main") or soup
    )
    for a in content_area.find_all("a", href=True):
        href = a.get("href", "").strip()
        title = a.get_text(separator=" ", strip=True)
        if not is_real_doc(href, title):
            continue
        url = _abs_url(href)
        uid = _make_uid(source_type, url, title)
        items.append({"title": title, "url": url, "date": "",
                      "source_type": source_type, "unique_id": uid})

    return items


# ─── SCRAPER 3: ITAT Case Laws ────────────────────────────────────────────────

def scrape_caselaws():
    source_type = "Case Law"
    logger.info("Scraping ITAT case laws...")

    items = []

    for url in [
        "https://itatonline.org/digest/all-judgements/",
        "https://itatonline.org/digest/",
    ]:
        soup = _fetch(url)
        if not soup:
            continue
        found = _parse_itatonline(soup, source_type)
        if found:
            logger.info(f"Found {len(found)} case laws from {url}")
            items.extend(found)
            break

    if items:
        for pg in [2, 3]:
            ps = _fetch(f"https://itatonline.org/digest/all-judgements/page/{pg}/")
            if ps:
                items.extend(_parse_itatonline(ps, source_type))

    if not items:
        logger.warning("itatonline failed, trying taxguru ITAT fallback")
        items = _scrape_taxguru_mirror("https://taxguru.in/income-tax/itat/", source_type)

    if not items:
        logger.warning("taxguru failed, trying indiankanoon fallback")
        items = _scrape_indiankanoon()

    items = _dedup(items)
    logger.info(f"Total case laws scraped: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


def _parse_itatonline(soup, source_type):
    items = []
    skip = {"home", "about", "contact", "login", "register",
            "all judgements", "digest", "category", "tag", "more"}

    for article in soup.find_all("article"):
        title_tag = article.find(["h1", "h2", "h3"])
        if not title_tag:
            continue
        link_tag = title_tag.find("a", href=True) or article.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title = title_tag.get_text(separator=" ", strip=True)
        if not title or len(title) < 10 or title.lower().strip() in skip:
            continue
        date_str = ""
        dt = article.find("time") or article.find(class_=re.compile(r"date|posted|published", re.I))
        if dt:
            date_str = _parse_date(dt.get("datetime", "") or dt.get_text(strip=True))
        if not href.startswith("http"):
            href = urljoin("https://itatonline.org", href)
        uid = _make_uid(source_type, href, title)
        items.append({"title": title, "url": href, "date": date_str,
                      "source_type": source_type, "unique_id": uid})

    if items:
        return items

    for heading in soup.find_all(["h2", "h3"]):
        link_tag = heading.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(separator=" ", strip=True)
        if not title or len(title) < 10 or title.lower().strip() in skip:
            continue
        if not href.startswith("http"):
            href = urljoin("https://itatonline.org", href)
        uid = _make_uid(source_type, href, title)
        items.append({"title": title, "url": href, "date": "",
                      "source_type": source_type, "unique_id": uid})

    return items


# ─── Mirror/Fallback Scrapers ─────────────────────────────────────────────────

def _scrape_taxguru_mirror(url, source_type):
    soup = _fetch(url)
    if not soup:
        return []
    items = []
    for article in soup.find_all("article"):
        title_tag = article.find(["h2", "h3"])
        if not title_tag:
            continue
        link_tag = title_tag.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        date_str = ""
        dt = article.find("time")
        if dt:
            date_str = _parse_date(dt.get("datetime", "") or dt.get_text())
        uid = _make_uid(source_type, href, title)
        items.append({"title": title, "url": href, "date": date_str,
                      "source_type": source_type, "unique_id": uid})
    logger.info(f"taxguru mirror ({url}): {len(items)} items")
    return items


def _scrape_indiankanoon():
    source_type = "Case Law"
    url = "https://indiankanoon.org/search/?formInput=Income+Tax+Appellate+Tribunal&pagenum=0"
    soup = _fetch(url)
    if not soup:
        return []
    items = []
    for result in soup.find_all("div", class_=re.compile(r"result", re.I)):
        link_tag = result.find("a", href=True)
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        if not href.startswith("http"):
            href = "https://indiankanoon.org" + href
        uid = _make_uid(source_type, href, title)
        items.append({"title": title, "url": href, "date": "",
                      "source_type": source_type, "unique_id": uid})
    logger.info(f"indiankanoon fallback: {len(items)} items")
    return items
