"""
src/scrapers.py

Uses Playwright headless browser to bypass 403 bot-blocking on:
- incometaxindia.gov.in  (notifications + circulars)
- itatonline.org         (ITAT case laws)

Playwright renders the page like a real browser — no 403, no bot detection.
Only official sources. No fallbacks to third-party sites.
"""

import hashlib
import re
import time
from datetime import datetime
from typing import List, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config.settings import SOURCES, MAX_ITEMS_PER_RUN
from src.logger import get_logger

logger = get_logger("scrapers")

_ITI_BASE = "https://www.incometaxindia.gov.in"

# ─── Playwright fetch ──────────────────────────────────────────────────────────

def _playwright_fetch(url: str, wait_selector: str = None, timeout: int = 30000) -> str:
    """
    Fetch a URL using Playwright headless Chromium.
    Returns full rendered HTML string, or empty string on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("Playwright not installed")
        return ""

    for attempt in range(1, 3):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-zygote",
                        "--single-process",
                    ],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    extra_http_headers={
                        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                # Wait for content to load
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=10000)
                    except Exception:
                        pass  # proceed even if selector not found
                else:
                    # General wait for network to settle
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass

                html = page.content()
                browser.close()
                logger.debug(f"Playwright fetched {url} — {len(html)} chars")
                return html

        except PWTimeout:
            logger.warning(f"Playwright timeout on attempt {attempt} for {url}")
        except Exception as e:
            logger.warning(f"Playwright attempt {attempt} failed for {url}: {e}")

        if attempt < 2:
            time.sleep(3)

    logger.error(f"Playwright failed after 2 attempts: {url}")
    return ""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_uid(source_type: str, url: str, title: str) -> str:
    raw = f"{source_type}|{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_DATE_FMTS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y", "%d.%m.%Y",
]

def _parse_date(raw: str) -> str:
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


def _dedup(items: List[Dict]) -> List[Dict]:
    seen, result = set(), []
    for item in items:
        uid = item.get("unique_id", "")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(item)
    return result


def _abs_url(href: str) -> str:
    href = href.strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return _ITI_BASE + href
    return _ITI_BASE + "/" + href


_SKIP_TITLES = {
    "home", "sitemap", "contact", "feedback", "login", "logout",
    "back", "next", "previous", "print", "share", "search",
    "english", "hindi", "about us", "disclaimer", "privacy",
    "help", "faq", "subscribe", "notifications", "circulars",
    "press releases", "skip to main content", "screen reader access",
    "accessibility statement", "register",
}

_SKIP_HREF_PARTS = [
    "javascript:", "mailto:", "facebook", "twitter",
    "youtube", "instagram", "linkedin",
]

def _is_real_doc(href: str, title: str) -> bool:
    if not href or not title:
        return False
    if len(title.strip()) < 8:
        return False
    title_l = title.lower().strip()
    if title_l in _SKIP_TITLES:
        return False
    if href.strip() in ("#", "/", ""):
        return False
    for bad in _SKIP_HREF_PARTS:
        if bad in href.lower():
            return False
    # Positive signals
    href_l = href.lower()
    is_pdf        = ".pdf" in href_l
    has_number    = bool(re.search(r'\d{1,4}[/\-_]\d{2,4}', title))
    has_keyword   = bool(re.search(
        r'(notification|circular|order|instruction|press|guideline|'
        r'amendment|clarif|cbdt|income.?tax|rule\s*\d|section\s*\d)',
        title, re.IGNORECASE
    ))
    in_comms_path = any(x in href_l for x in [
        "/communications/", "notification_", "circular_",
        "/notification/", "/circular/",
    ])
    return is_pdf or has_number or has_keyword or in_comms_path


# ─── SCRAPER 1: Notifications ─────────────────────────────────────────────────

def scrape_notifications() -> List[Dict]:
    source_type = "Notification"
    url = SOURCES["notifications"]["url"]
    logger.info(f"Scraping notifications from {url}")

    html = _playwright_fetch(url, wait_selector="table,ul,li,a")
    if not html:
        logger.error("Failed to fetch notifications page")
        return []

    items = _parse_iti_page(html, source_type)
    items = _dedup(items)
    logger.info(f"Notifications found: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


# ─── SCRAPER 2: Circulars ─────────────────────────────────────────────────────

def scrape_circulars() -> List[Dict]:
    source_type = "Circular"
    url = SOURCES["circulars"]["url"]
    logger.info(f"Scraping circulars from {url}")

    html = _playwright_fetch(url, wait_selector="table,ul,li,a")
    if not html:
        logger.error("Failed to fetch circulars page")
        return []

    items = _parse_iti_page(html, source_type)
    items = _dedup(items)
    logger.info(f"Circulars found: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


def _parse_iti_page(html: str, source_type: str) -> List[Dict]:
    """Parse incometaxindia.gov.in listing page HTML into items."""
    soup = BeautifulSoup(html, "lxml")
    items = []

    # Strategy 1: Table rows (primary layout)
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            link_tag = row.find("a", href=True)
            if not link_tag:
                continue
            href  = link_tag.get("href", "").strip()
            title = link_tag.get_text(separator=" ", strip=True)
            if not _is_real_doc(href, title):
                continue
            abs_url = _abs_url(href)
            if not abs_url:
                continue
            # Find date in row cells
            date_str = ""
            for cell in row.find_all(["td", "th"]):
                text = cell.get_text(strip=True)
                m = re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", text)
                if m:
                    date_str = _parse_date(m.group())
                    break
            uid = _make_uid(source_type, abs_url, title)
            items.append({
                "title": title, "url": abs_url, "date": date_str,
                "source_type": source_type, "unique_id": uid,
            })

    if items:
        logger.debug(f"Table strategy: {len(items)} items")
        return items

    # Strategy 2: Content div links
    content = (
        soup.find("div", id=re.compile(r"content|main|body", re.I)) or
        soup.find("div", class_=re.compile(r"content|main|listing", re.I)) or
        soup.find("main") or
        soup.find("body") or
        soup
    )
    for a in content.find_all("a", href=True):
        href  = a.get("href", "").strip()
        title = a.get_text(separator=" ", strip=True)
        if not _is_real_doc(href, title):
            continue
        abs_url = _abs_url(href)
        if not abs_url:
            continue
        uid = _make_uid(source_type, abs_url, title)
        items.append({
            "title": title, "url": abs_url, "date": "",
            "source_type": source_type, "unique_id": uid,
        })

    logger.debug(f"Link strategy: {len(items)} items")
    return items


# ─── SCRAPER 3: ITAT Case Laws ────────────────────────────────────────────────

def scrape_caselaws() -> List[Dict]:
    source_type = "Case Law"
    base_url = SOURCES["caselaws"]["url"]
    logger.info(f"Scraping case laws from {base_url}")

    items = []
    for page_num in [1, 2, 3]:
        if page_num == 1:
            url = base_url
        else:
            url = f"https://itatonline.org/digest/all-judgements/page/{page_num}/"

        html = _playwright_fetch(url, wait_selector="article,h2,h3")
        if not html:
            logger.warning(f"No HTML from page {page_num}, stopping")
            break

        page_items = _parse_itatonline(html, source_type)
        logger.info(f"Case laws page {page_num}: {len(page_items)} items")
        items.extend(page_items)

        if not page_items:
            break

    items = _dedup(items)
    logger.info(f"Total case laws: {len(items)}")
    return items[:MAX_ITEMS_PER_RUN]


def _parse_itatonline(html: str, source_type: str) -> List[Dict]:
    """Parse itatonline.org/digest listing page."""
    soup = BeautifulSoup(html, "lxml")
    items = []

    skip = {
        "home", "about", "contact", "login", "register",
        "all judgements", "digest", "category", "tag", "more",
        "next", "previous", "back",
    }

    # WordPress article pattern (primary)
    for article in soup.find_all("article"):
        title_tag = article.find(["h1", "h2", "h3"])
        if not title_tag:
            continue
        link_tag = title_tag.find("a", href=True) or article.find("a", href=True)
        if not link_tag:
            continue
        href  = link_tag.get("href", "").strip()
        title = title_tag.get_text(separator=" ", strip=True)
        if not title or len(title) < 10 or title.lower().strip() in skip:
            continue
        # Date
        date_str = ""
        dt = (
            article.find("time") or
            article.find(class_=re.compile(r"date|posted|published", re.I))
        )
        if dt:
            date_str = _parse_date(dt.get("datetime", "") or dt.get_text(strip=True))
        if not href.startswith("http"):
            href = urljoin("https://itatonline.org", href)
        uid = _make_uid(source_type, href, title)
        items.append({
            "title": title, "url": href, "date": date_str,
            "source_type": source_type, "unique_id": uid,
        })

    if items:
        return items

    # Fallback: h2/h3 headings with links
    for heading in soup.find_all(["h2", "h3"]):
        link_tag = heading.find("a", href=True)
        if not link_tag:
            continue
        href  = link_tag.get("href", "").strip()
        title = link_tag.get_text(separator=" ", strip=True)
        if not title or len(title) < 10 or title.lower().strip() in skip:
            continue
        if not href.startswith("http"):
            href = urljoin("https://itatonline.org", href)
        uid = _make_uid(source_type, href, title)
        items.append({
            "title": title, "url": href, "date": "",
            "source_type": source_type, "unique_id": uid,
        })

    return items
