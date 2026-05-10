"""
src/content_extractor.py
Extract clean text from HTML pages and PDFs.
Uses requests for PDF download, BeautifulSoup for HTML cleaning.
"""

import io
import re
import time
from typing import Tuple

import requests
from bs4 import BeautifulSoup

from config.settings import REQUEST_TIMEOUT
from src.logger import get_logger

logger = get_logger("content_extractor")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_JUNK_TAGS = ["script","style","nav","footer","header","noscript","aside","iframe","form","button"]
_JUNK_CLS  = re.compile(
    r"(nav|navbar|menu|footer|header|sidebar|breadcrumb|pagination|"
    r"cookie|popup|modal|social|share|search|login|topbar|toolbar|ad-|banner)",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(l) > 3]
    deduped, prev = [], None
    for l in lines:
        if l != prev:
            deduped.append(l)
        prev = l
    return "\n".join(deduped).strip()


def extract_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_JUNK_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        cls = " ".join(tag.get("class", []))
        tid = tag.get("id", "")
        if _JUNK_CLS.search(cls) or _JUNK_CLS.search(tid):
            tag.decompose()

    for selector in ["article", "main",
                     lambda s: s.find(attrs={"class": re.compile("content|article|post|entry|body", re.I)}),
                     "body"]:
        if callable(selector):
            el = selector(soup)
        else:
            el = soup.find(selector)
        if el:
            t = el.get_text(separator="\n")
            if len(t.strip()) > 100:
                return _clean(t)

    return _clean(soup.get_text(separator="\n"))


def extract_pdf(pdf_bytes: bytes) -> str:
    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parts = [p.extract_text() for p in pdf.pages[:15] if p.extract_text()]
            text = "\n".join(parts)
            if text.strip():
                return _clean(text)
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")

    # PyPDF2 fallback
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages[:15]:
            try:
                t = page.extract_text()
                if t:
                    parts.append(t)
            except Exception:
                pass
        text = "\n".join(parts)
        if text.strip():
            return _clean(text)
    except Exception as e:
        logger.warning(f"PyPDF2 failed: {e}")

    return ""


def fetch_content(url: str) -> Tuple[str, str]:
    """
    Fetch URL and extract clean text.
    Returns (text, content_type) where content_type is 'html' or 'pdf'.
    """
    for attempt in range(1, 3):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT,
                                allow_redirects=True, verify=False)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "pdf" in ct.lower() or url.lower().endswith(".pdf"):
                return extract_pdf(resp.content), "pdf"
            else:
                return extract_html(resp.text), "html"
        except Exception as e:
            logger.warning(f"Content fetch attempt {attempt} failed for {url}: {e}")
            if attempt < 2:
                time.sleep(2)

    return "", "error"


def summarize(text: str, max_chars: int = 500, max_sents: int = 3) -> str:
    if not text:
        return "No content available."
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    parts, total = [], 0
    for s in sentences[:15]:
        if total + len(s) > max_chars or len(parts) >= max_sents:
            break
        parts.append(s)
        total += len(s)
    if parts:
        return " ".join(parts)
    return text[:max_chars].strip() + ("…" if len(text) > max_chars else "")
