"""
src/scrapers.py — Scrape incometaxindia.gov.in and itatonline.org
Uses only requests + BeautifulSoup (no Playwright dependency).
"""

import hashlib
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import REQUEST_HEADERS, REQUEST_TIMEOUT, SOURCES
from src.logger import get_logger

logger = get_logger("scrapers")

BASE_ITX   = "https://www.incometax.gov.in"
BASE_ITX_OLD = "https://incometaxindia.gov.in"
BASE_ITAT  = "https://www.itatonline.org"

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, retries: int = 3) -> requests.Response | None:
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.warning(f"GET {url} attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return None


def _uid(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()[:16]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_date(text: str) -> str:
    """Try to parse a date string; return ISO or original."""
    from dateutil import parser as dparser
    text = _clean(text)
    try:
        return dparser.parse(text, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Notifications scraper
# ---------------------------------------------------------------------------

def scrape_notifications() -> list[dict]:
    items = []
    cfg   = SOURCES["notifications"]

    for base_url in cfg["urls"]:
        logger.info(f"Trying notifications URL: {base_url}")
        resp = _get(base_url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        items = _parse_incometax_listing(soup, base_url, "notification")
        if items:
            logger.info(f"Notifications: found {len(items)} items from {base_url}")
            break

        # Fallback: look for direct links on the old domain
        items = _parse_incometax_old(soup, base_url, "notification")
        if items:
            logger.info(f"Notifications (fallback): found {len(items)} items")
            break

    return items


# ---------------------------------------------------------------------------
# Circulars scraper
# ---------------------------------------------------------------------------

def scrape_circulars() -> list[dict]:
    items = []
    cfg   = SOURCES["circulars"]

    for base_url in cfg["urls"]:
        logger.info(f"Trying circulars URL: {base_url}")
        resp = _get(base_url)
        if not resp:
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        items = _parse_incometax_listing(soup, base_url, "circular")
        if items:
            logger.info(f"Circulars: found {len(items)} items from {base_url}")
            break

        items = _parse_incometax_old(soup, base_url, "circular")
        if items:
            logger.info(f"Circulars (fallback): found {len(items)} items")
            break

    return items


# ---------------------------------------------------------------------------
# Case laws scraper
# ---------------------------------------------------------------------------

def scrape_caselaws() -> list[dict]:
    items = []
    cfg   = SOURCES["caselaws"]

    for base_url in cfg["urls"]:
        logger.info(f"Trying caselaws URL: {base_url}")
        resp = _get(base_url)
        if not resp:
            continue

        soup  = BeautifulSoup(resp.text, "lxml")
        items = _parse_itat(soup, base_url)
        if items:
            logger.info(f"Case laws: found {len(items)} items")
            break

    return items


# ---------------------------------------------------------------------------
# Parser: incometax.gov.in (new portal)
# ---------------------------------------------------------------------------

def _parse_incometax_listing(soup: BeautifulSoup, base_url: str, source_type: str) -> list[dict]:
    items = []

    # Strategy 1: table rows with anchor links
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        link_tag = row.find("a", href=True)
        if not link_tag:
            continue

        href  = link_tag["href"].strip()
        if not href or href in ("#", "javascript:void(0)"):
            continue

        url   = href if href.startswith("http") else urljoin(base_url, href)
        title = _clean(link_tag.get_text())
        if not title or len(title) < 5:
            # try all cell text
            title = _clean(" ".join(c.get_text() for c in cells))

        # date: look for a cell that looks like a date
        date_str = ""
        for cell in cells:
            txt = _clean(cell.get_text())
            if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2}", txt):
                date_str = _parse_date(txt)
                break

        uid = _uid(url + title)
        items.append({
            "unique_id":   uid,
            "title":       title,
            "url":         url,
            "date":        date_str,
            "source_type": source_type,
        })

    # Strategy 2: list items / div cards with links
    if not items:
        for a in soup.select("ul li a[href], div.item a[href], div.card a[href], .content-area a[href]"):
            href  = a["href"].strip()
            if not href or href in ("#", "javascript:void(0)"):
                continue
            url   = href if href.startswith("http") else urljoin(base_url, href)
            title = _clean(a.get_text())
            if not title or len(title) < 10:
                continue
            # filter only relevant links (PDFs or notification/circular pages)
            if not any(k in url.lower() for k in ["notif", "circular", "pdf", "communicat"]):
                continue
            uid = _uid(url + title)
            items.append({
                "unique_id":   uid,
                "title":       title,
                "url":         url,
                "date":        "",
                "source_type": source_type,
            })

    return items[:50]  # cap at 50 per run


def _parse_incometax_old(soup: BeautifulSoup, base_url: str, source_type: str) -> list[dict]:
    """Fallback for old incometaxindia.gov.in structure."""
    items = []
    for a in soup.find_all("a", href=True):
        href  = a["href"].strip()
        title = _clean(a.get_text())
        if not title or len(title) < 10:
            continue
        if not any(ext in href.lower() for ext in [".pdf", ".htm", ".html", "notification", "circular"]):
            continue
        url = href if href.startswith("http") else urljoin(base_url, href)
        uid = _uid(url + title)
        items.append({
            "unique_id":   uid,
            "title":       title,
            "url":         url,
            "date":        "",
            "source_type": source_type,
        })
    return items[:50]


# ---------------------------------------------------------------------------
# Parser: itatonline.org
# ---------------------------------------------------------------------------

def _parse_itat(soup: BeautifulSoup, base_url: str) -> list[dict]:
    items = []

    # Strategy 1: article/post titles
    selectors = [
        "h2.entry-title a",
        "h3.entry-title a",
        ".post-title a",
        "article h2 a",
        "article h3 a",
        ".jeg_post_title a",
        "h2 a",
    ]
    for sel in selectors:
        for a in soup.select(sel):
            href  = a.get("href", "").strip()
            title = _clean(a.get_text())
            if not href or not title or len(title) < 10:
                continue
            url = href if href.startswith("http") else urljoin(base_url, href)

            # Try to find the date near this element
            date_str = ""
            parent   = a.find_parent(["article", "div", "li"])
            if parent:
                date_tag = parent.find(class_=re.compile(r"date|time|meta", re.I))
                if date_tag:
                    date_str = _parse_date(date_tag.get_text())

            uid = _uid(url + title)
            items.append({
                "unique_id":   uid,
                "title":       title,
                "url":         url,
                "date":        date_str,
                "source_type": "caselaw",
            })
        if items:
            break

    # Strategy 2: any anchor whose text looks like a case citation
    if not items:
        citation_re = re.compile(
            r"(ITA\s*No|CIT\s*v|ITAT|Income\s*Tax\s*Appeal|Tribunal)", re.I
        )
        for a in soup.find_all("a", href=True):
            title = _clean(a.get_text())
            if citation_re.search(title) and len(title) > 15:
                href  = a["href"].strip()
                url   = href if href.startswith("http") else urljoin(base_url, href)
                uid   = _uid(url + title)
                items.append({
                    "unique_id":   uid,
                    "title":       title,
                    "url":         url,
                    "date":        "",
                    "source_type": "caselaw",
                })

    # Deduplicate by uid
    seen: set = set()
    deduped   = []
    for item in items:
        if item["unique_id"] not in seen:
            seen.add(item["unique_id"])
            deduped.append(item)

    return deduped[:30]
