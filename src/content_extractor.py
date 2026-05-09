"""
src/content_extractor.py
Robustly extracts clean readable text from HTML pages and PDF documents.
Removes navigation, scripts, footers, and other junk.
"""

import io
import re
import time
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config.settings import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, USER_AGENT
from src.logger import get_logger

logger = get_logger("content_extractor")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def fetch_url(url: str, retries: int = MAX_RETRIES) -> Optional[requests.Response]:
    """Fetch a URL with retries. Returns Response or None."""
    for attempt in range(1, retries + 1):
        try:
            resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt}/{retries} failed for {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    logger.error(f"All fetch attempts failed for {url}")
    return None


def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf") or "pdf" in url.lower()


def is_pdf_response(resp: requests.Response) -> bool:
    ct = resp.headers.get("Content-Type", "")
    return "pdf" in ct.lower() or is_pdf_url(resp.url)


# ─── PDF Extraction ───────────────────────────────────────────────────────────

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes. Tries pdfplumber first, then PyPDF2 as fallback."""
    text = ""

    # Strategy 1: pdfplumber (best quality)
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages[:20]:  # limit to first 20 pages
                pg_text = page.extract_text()
                if pg_text:
                    pages_text.append(pg_text)
            text = "\n".join(pages_text)
        if text.strip():
            return _clean_text(text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")

    # Strategy 2: PyPDF2 fallback
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages[:20]):
            try:
                pg_text = page.extract_text()
                if pg_text:
                    pages_text.append(pg_text)
            except Exception:
                pass
        text = "\n".join(pages_text)
        if text.strip():
            return _clean_text(text)
    except Exception as e:
        logger.warning(f"PyPDF2 extraction failed: {e}")

    logger.warning("PDF extraction produced no text")
    return ""


# ─── HTML Extraction ──────────────────────────────────────────────────────────

# Tags to remove entirely before extracting text
_JUNK_TAGS = [
    "script", "style", "nav", "footer", "header",
    "noscript", "aside", "iframe", "form",
    "meta", "link", "button", "select", "input",
]

# CSS classes/ids that strongly suggest navigation/chrome
_JUNK_PATTERNS = re.compile(
    r"(nav|navbar|menu|footer|header|sidebar|breadcrumb|pagination|"
    r"cookie|popup|modal|social|share|search|login|signup|ad-|banner|"
    r"related|recommend|trending|topbar|bottombar|toolbar)",
    re.IGNORECASE,
)


def extract_text_from_html(html: str, base_url: str = "") -> str:
    """
    Intelligently extract clean article content from HTML.
    Tries multiple strategies in order of quality.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove junk tags
    for tag in soup(_JUNK_TAGS):
        tag.decompose()

    # Remove junk by class/id
    for tag in soup.find_all(True):
        cls = " ".join(tag.get("class", []))
        tid = tag.get("id", "")
        if _JUNK_PATTERNS.search(cls) or _JUNK_PATTERNS.search(tid):
            tag.decompose()

    # Strategy 1: <article> tag
    article = soup.find("article")
    if article:
        text = article.get_text(separator="\n")
        if len(text.strip()) > 200:
            return _clean_text(text)

    # Strategy 2: <main> tag
    main = soup.find("main")
    if main:
        text = main.get_text(separator="\n")
        if len(text.strip()) > 200:
            return _clean_text(text)

    # Strategy 3: div with content-like class
    for cls_name in ["content", "article", "post", "entry", "body", "main-content", "page-content"]:
        tag = soup.find(attrs={"class": re.compile(cls_name, re.I)})
        if tag:
            text = tag.get_text(separator="\n")
            if len(text.strip()) > 200:
                return _clean_text(text)

    # Strategy 4: largest <div> block by text length
    divs = soup.find_all("div")
    if divs:
        best = max(divs, key=lambda d: len(d.get_text()))
        text = best.get_text(separator="\n")
        if len(text.strip()) > 100:
            return _clean_text(text)

    # Strategy 5: full body fallback
    body = soup.find("body")
    if body:
        return _clean_text(body.get_text(separator="\n"))

    return _clean_text(soup.get_text(separator="\n"))


def _clean_text(text: str) -> str:
    """Remove whitespace noise and normalize text."""
    # Collapse whitespace lines
    lines = [line.strip() for line in text.splitlines()]
    # Remove empty lines and very short lines (likely nav fragments)
    lines = [l for l in lines if len(l) > 3]
    # Remove duplicate adjacent lines
    deduped = []
    prev = None
    for l in lines:
        if l != prev:
            deduped.append(l)
        prev = l
    return "\n".join(deduped).strip()


# ─── Unified Extractor ────────────────────────────────────────────────────────

def extract_content_from_url(url: str) -> Tuple[str, str]:
    """
    Fetch URL and extract clean text content.
    Returns (extracted_text, content_type) where content_type is 'html' or 'pdf'.
    """
    resp = fetch_url(url)
    if resp is None:
        return ("", "error")

    if is_pdf_response(resp):
        text = extract_text_from_pdf_bytes(resp.content)
        return (text, "pdf")
    else:
        text = extract_text_from_html(resp.text, base_url=url)
        return (text, "html")


# ─── Summarizer ───────────────────────────────────────────────────────────────

def simple_summarize(text: str, max_chars: int = 600, max_lines: int = 3) -> str:
    """
    Extract a concise summary from text without external AI APIs.
    Takes first meaningful sentences up to max_chars.
    """
    if not text:
        return "No content available."

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    summary_parts = []
    total = 0
    for sent in sentences[:15]:
        if total + len(sent) > max_chars:
            break
        summary_parts.append(sent)
        total += len(sent)
        if len(summary_parts) >= max_lines:
            break

    if not summary_parts:
        # fallback: first N chars
        return text[:max_chars].strip() + ("…" if len(text) > max_chars else "")

    return " ".join(summary_parts)
