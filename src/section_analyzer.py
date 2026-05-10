"""
src/section_analyzer.py — Detect Indian Income Tax Act section references.
"""

import re
from functools import lru_cache
from typing import List

from src.logger import get_logger

logger = get_logger("section_analyzer")

# Patterns that match section references like:
#   section 80C, s. 148, sec. 194J, u/s 10(38), Section 271AAC
_SECTION_PATTERN = re.compile(
    r"""
    (?:
        (?:section|sec(?:tion)?\.?|u/s|u\.?s\.?)   # keyword
        \s*
    )?
    \b
    (
        \d{1,3}                   # number (1–3 digits)
        [A-Z]{0,4}                # optional suffix letters
        (?:\([^)]{1,10}\))?       # optional sub-section like (1) or (38)
    )
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Normalise to uppercase without sub-section for dedup
_NORMALISE = re.compile(r"\([^)]*\)")

# Known valid section numbers (prevents matching random numbers)
_KNOWN_SECTIONS = {
    "2", "4", "5", "6", "9", "10", "10A", "10AA", "10B", "10C",
    "11", "12", "12A", "12AA", "12AB", "13", "14", "14A",
    "17", "22", "24", "28", "32", "35",
    "40", "40A", "41", "43",
    "44", "44AB", "44AD", "44ADA", "44AE", "44BB", "44BBA",
    "45", "47", "48", "49", "50", "50C", "50CA", "54", "54B", "54EC", "54F",
    "56", "57", "58",
    "68", "69", "69A", "69B", "69C", "69D",
    "80C", "80CCC", "80CCD", "80D", "80DD", "80DDB",
    "80E", "80EE", "80EEA", "80EEB",
    "80G", "80GG", "80GGA", "80GGC",
    "80IA", "80IAB", "80IAC", "80IB", "80IC", "80ID",
    "80JJA", "80JJAA",
    "80P", "80QQB", "80RRB",
    "80U",
    "87A",
    "90", "90A", "91",
    "92", "92A", "92B", "92C", "92CA", "92CB",
    "115A", "115BAA", "115BAB", "115BAC", "115BAD",
    "115JB", "115JC", "115JD",
    "115QA", "115R", "115T",
    "115UA", "115UB",
    "119", "120", "124",
    "131", "132", "132A", "133", "133A", "133B", "133C",
    "139", "139A", "139AA", "139C",
    "142", "142A", "143", "144", "144A", "144B", "144C",
    "145", "145A", "145B",
    "147", "148", "148A",
    "149", "150", "151", "151A",
    "153", "153A", "153B", "153C", "153D",
    "154", "156", "158B", "158BC", "158BD",
    "192", "192A",
    "193", "194", "194A", "194B", "194BA", "194BB", "194C",
    "194D", "194DA", "194E", "194EE", "194F", "194G",
    "194H", "194I", "194IA", "194IB", "194IC",
    "194J", "194K", "194LA", "194LB", "194LC", "194LD",
    "194M", "194N", "194O", "194P", "194Q", "194R", "194S",
    "195", "196", "196A", "196B", "196C", "196D",
    "197", "197A", "198", "199", "200", "200A",
    "201", "203", "203A", "203AA", "206",
    "206AA", "206AB", "206C", "206CA", "206CB", "206CC", "206CR",
    "220", "221", "222", "225", "226", "227", "228",
    "234A", "234B", "234C", "234D", "234E", "234F",
    "237", "239", "240", "241A", "242", "243", "244", "244A",
    "245", "245A", "245C", "245D", "245H", "245MA",
    "246", "246A", "249", "250", "251", "252", "253", "254",
    "255", "256", "260A",
    "261", "263", "264", "265", "268", "268A",
    "269", "269SS", "269ST", "269SU", "269T",
    "270A", "270AA", "271", "271A", "271AA", "271AAA", "271AAB",
    "271AAC", "271B", "271BA", "271C", "271CA", "271D", "271DA",
    "271DB", "271E", "271F", "271FA", "271FAA", "271FAB",
    "271G", "271H", "271I", "271J",
    "272A", "272AA", "272B", "273", "273A", "273AA", "273B",
    "274", "275", "276", "276A", "276AB", "276B", "276BB",
    "276C", "276CC", "276D", "277", "277A", "278", "278A", "278AB",
    "278B", "278C", "278D", "279", "280",
    "281", "281B", "282", "282A", "285", "285A", "285B", "285BA",
    "286", "288", "288A", "288B",
    "292", "292B", "292BB", "292C",
}


def detect_sections(text: str) -> List[str]:
    """Return a sorted, deduplicated list of section numbers found in text."""
    if not text:
        return []

    found: set[str] = set()
    for m in _SECTION_PATTERN.finditer(text):
        raw = m.group(1).upper()
        # strip sub-section for lookup
        base = _NORMALISE.sub("", raw).strip()
        if base in _KNOWN_SECTIONS:
            found.add(base)

    return sorted(found, key=_section_sort_key)


def _section_sort_key(s: str):
    """Sort sections numerically then alphabetically."""
    num  = re.match(r"(\d+)", s)
    suf  = re.sub(r"^\d+", "", s)
    return (int(num.group(1)) if num else 9999, suf)


def sections_display(sections: List[str]) -> str:
    """Return a formatted string like '§80C, §148, §194J'."""
    return ", ".join(f"§{s}" for s in sections)
