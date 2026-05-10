"""
src/content_extractor.py — Fetch and extract clean text from URLs (HTML or PDF).
No Playwright — pure requests.
"""

import io
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import REQUEST_HEADERS, REQUEST_TIMEOUT
from src.logger import get_logger

logger = get_logger("content_extractor")

SESSION = requests.Session()
SESSION.headers.update(REQUEST_HEADERS)

_BOILERPLATE = re.compile(
    r"(cookie|privacy policy|terms of use|skip to (main )?content|"
    r"javascript is (disabled|required)|all rights reserved)",
    re.I,
)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_content(url: str) -> tuple[str, str]:
    """
    Returns (content_text, content_type) where content_type is one of:
      'pdf', 'html', 'none'
    """
    if not url or not url.startswith("http"):
        return "", "none"

    try:
        resp = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"fetch_content GET failed for {url}: {e}")
        return "", "none"

    ct = resp.headers.get("Content-Type", "").lower()

    # PDF
    if "pdf" in ct or url.lower().endswith(".pdf"):
        text = _extract_pdf(resp.content)
        return text, "pdf"

    # HTML
    text = _extract_html(resp.text)
    return text, "html"


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _extract_pdf(content: bytes) -> str:
    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages[:10]:  # cap at 10 pages
                txt = page.extract_text()
                if txt:
                    pages.append(txt.strip())
            text = "\n\n".join(pages)
            if text.strip():
                return text
    except Exception as e:
        logger.debug(f"pdfplumber failed: {e}")

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages  = []
        for page in reader.pages[:10]:
            txt = page.extract_text()
            if txt:
                pages.append(txt.strip())
        return "\n\n".join(pages)
    except Exception as e:
        logger.debug(f"PyPDF2 failed: {e}")

    return ""


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------

def _extract_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Remove noise tags
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "form", "noscript", "iframe"]):
        tag.decompose()

    # Try to find the main content area
    main = (
        soup.find("main")
        or soup.find(id=re.compile(r"main|content|article", re.I))
        or soup.find(class_=re.compile(r"main|content|article|post-body|entry", re.I))
        or soup.find("article")
        or soup.body
    )

    if main is None:
        return ""

    lines = []
    for text in main.stripped_strings:
        line = re.sub(r"\s+", " ", text).strip()
        if len(line) < 4:
            continue
        if _BOILERPLATE.search(line):
            continue
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summarizer (simple extractive; no LLM dependency)
# ---------------------------------------------------------------------------

def summarize(content: str, max_chars: int = 800) -> str:
    """
    Extractive summarisation: return the first meaningful sentences up to max_chars.
    Falls back to first max_chars chars if sentence splitting fails.
    """
    if not content:
        return ""

    content = re.sub(r"\n{3,}", "\n\n", content.strip())

    # Split into sentences on '. ', '.\n', '! ', '? '
    sentences = re.split(r"(?<=[.!?])\s+", content)
    result    = []
    length    = 0

    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 10:
            continue
        if length + len(sent) > max_chars:
            break
        result.append(sent)
        length += len(sent) + 1

    summary = " ".join(result) if result else content[:max_chars]
    if len(content) > max_chars:
        summary = summary.rstrip(".") + "…"
    return summary
