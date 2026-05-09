"""
src/section_analyzer.py
Detects Income Tax Act sections mentioned in text using regex.
Normalizes and deduplicates detected sections.
"""

import re
from typing import List

from config.settings import IMPORTANT_SECTIONS
from src.logger import get_logger

logger = get_logger("section_analyzer")

# ─── Regex patterns ───────────────────────────────────────────────────────────
# Matches patterns like: Section 80C, Sec. 194J, u/s 148, U/S 148A,
#   section 56(2)(x), s. 271AAC, 80-IC, 10(23C)(iiiad)
_SECTION_PATTERN = re.compile(
    r"""
    (?:
        (?:section|sec(?:tion)?s?|u[/\.]?s|under\s+section)
        [\s\.]*
    )?
    \b
    (
        \d{1,3}                     # base number
        (?:[A-Z]{1,4})?             # optional alpha suffix e.g. 194J, 139AA
        (?:\([^)]{1,15}\))*         # optional sub-clauses e.g. (1)(c)
        (?:[-/]\w{1,5})?            # optional suffix like -IA, -IC
    )
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Known false-positive numbers to filter out (years, percentages, page numbers)
_FALSE_POSITIVE_NUMBERS = {
    "2023", "2024", "2022", "2021", "2020", "2019", "2018", "2017",
    "100", "200", "300", "400", "500", "1000",
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
}

# Valid IT Act section range: 1–298 + special alphanumeric
_VALID_SECTION_RE = re.compile(r"^\d{1,3}[A-Z]{0,4}(\([^)]+\))*(-[A-Z0-9]{1,5})?$", re.IGNORECASE)


def _normalize_section(raw: str) -> str:
    """Normalize section string to consistent format."""
    s = raw.strip()
    # uppercase letter suffixes
    s = re.sub(r"([0-9])([a-z]+)", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def detect_sections(text: str) -> List[str]:
    """
    Extract and return a deduplicated sorted list of detected IT sections
    from the given text.
    """
    if not text:
        return []

    matches = _SECTION_PATTERN.findall(text)
    seen = set()
    result = []

    for raw in matches:
        norm = _normalize_section(raw)

        # Filter false positives
        if norm in _FALSE_POSITIVE_NUMBERS:
            continue
        if not _VALID_SECTION_RE.match(norm):
            continue

        # Must start with a number in valid IT range
        base_num = re.match(r"(\d+)", norm)
        if not base_num:
            continue
        num = int(base_num.group(1))
        if num < 1 or num > 298:
            continue

        if norm not in seen:
            seen.add(norm)
            result.append(norm)

    return sorted(result, key=lambda s: (
        int(re.match(r"(\d+)", s).group(1)),
        s
    ))


def is_important(sections: List[str]) -> bool:
    """Return True if any detected section is in the IMPORTANT_SECTIONS list."""
    imp_set = set(s.upper() for s in IMPORTANT_SECTIONS)
    for sec in sections:
        if sec.upper() in imp_set:
            return True
    return False


def sections_display(sections: List[str]) -> str:
    """Format sections list for display."""
    if not sections:
        return "None detected"
    return ", ".join(f"§{s}" for s in sections)
