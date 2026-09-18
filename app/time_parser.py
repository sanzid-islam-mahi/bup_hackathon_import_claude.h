"""
Deterministic time-phrase parser for operator notes.

The LLM interprets "1 PM to 3 PM" as hours [13, 14] correctly in our tests,
but hidden paraphrases (e.g., "between 13:00 and 15:00", "6 PM until 9 PM",
"the 1-3 PM window") could trip it up. This module extracts hours
deterministically when possible, so the interpreter can use them as a hint.

Rules:
  - Return list of unique sorted hours (start inclusive, end EXCLUSIVE
    except for "X through Y" or "X until Y" where end is INCLUSIVE).
  - Wholly-hour convention: "1 PM" = 13, "noon" = 12, "midnight" = 0.
  - Hours in [0, 23] only. If ambiguous or out of range, return None.
  - Conservative: when uncertain, return None (let LLM decide).

Time phrases handled:
  - "X PM to Y PM" / "X PM until Y PM" / "X PM-Y PM" / "X-Y PM"
  - "between HH and HH" / "between HH:00 and HH:00"
  - "hours H through H" (inclusive both ends)
  - "from X to Y" / "from X:00 to Y:00"
  - "the morning" / "afternoon" / "evening" / "night"
"""
from __future__ import annotations

import re
from typing import List, Optional


def _to_24(hour: int, meridiem: str) -> Optional[int]:
    if not (1 <= hour <= 12):
        return None
    m = meridiem.lower()
    if m == "am":
        return 0 if hour == 12 else hour
    if m == "pm":
        return 12 if hour == 12 else hour + 12
    return None


def _hours_range(start: int, end: int, end_inclusive: bool) -> Optional[List[int]]:
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return None
    if end_inclusive:
        if end < start:
            return None
        return list(range(start, end + 1))
    else:
        if end <= start:
            return None
        return list(range(start, end))


# Inclusive pattern: "hours 13 through 15" or "13 through 15"
_RE_RANGE_THROUGH = re.compile(
    r"\b(?:hours?\s+)?(?P<sH>\d{1,2})\s+through\s+(?P<eH>\d{1,2})\b",
    re.IGNORECASE,
)

# 24-hour range: "13 to 15", "between 13 and 15", "from 13:00 to 15:00",
# "13-15" / "13:00-15:00". Captures digits + optional ":00" suffix.
_RE_RANGE_24H = re.compile(
    r"\b(?:from\s+|between\s+)?"
    r"(?P<sH>\d{1,2})(?::00)?"
    r"\s*(?:to|until|till|and|-|–|—)\s*"
    r"(?P<eH>\d{1,2})(?::00)?\b",
    re.IGNORECASE,
)

# Inclusive pattern (24h): "hours 13 through 15" or "13 through 15"
_RE_RANGE_THROUGH_24H = re.compile(
    r"\b(?:hours?\s+)?(?P<sH>\d{1,2})\s+through\s+(?P<eH>\d{1,2})\b",
    re.IGNORECASE,
)

# Word-time keywords: "noon", "midnight"
_KEYWORD_NOON = re.compile(r"\bnoon\b", re.IGNORECASE)
_KEYWORD_MIDNIGHT = re.compile(r"\bmidnight\b", re.IGNORECASE)

# 12-hour range: "1 PM to 3 PM", "1-3 PM" (shared meridiem),
# "6 PM until 9 PM", "from 1 PM to 3 PM", "between 1 PM and 3 PM"
# Both meridiems are captured (second optional, defaults to first).
_RE_RANGE_12H = re.compile(
    r"\b(?:from\s+|between\s+)?"
    r"(?P<sH>\d{1,2})"
    r"(?P<sM>\s*(?:AM|PM|am|pm))?"
    r"\s*(?:to|until|till|through|and|-|–|—)\s*"
    r"(?P<eH>\d{1,2})"
    r"(?P<eM>\s*(?:AM|PM|am|pm))?\b",
    re.IGNORECASE,
)

# Fuzzy time-of-day keywords (heuristic)
_FUZZY = [
    (re.compile(r"\b(?:the\s+)?morning\b", re.IGNORECASE), list(range(6, 12))),
    (re.compile(r"\b(?:the\s+)?afternoon\b", re.IGNORECASE), list(range(12, 17))),
    (re.compile(r"\b(?:the\s+)?evening\b", re.IGNORECASE), list(range(17, 23))),
    (re.compile(r"\b(?:the\s+)?night\b", re.IGNORECASE), list(range(20, 24)) + [0]),
]


def parse_hours(text: str) -> Optional[List[int]]:
    """Try to extract a list of hour indices from a note. Returns None if uncertain."""
    if not isinstance(text, str) or not text:
        return None

    # Most specific first: inclusive "X through Y" (24h version)
    m = _RE_RANGE_THROUGH_24H.search(text)
    if m:
        start = int(m.group("sH"))
        end = int(m.group("eH"))
        result = _hours_range(start, end, end_inclusive=True)
        if result is not None:
            return sorted(set(result))

    # Try 12-hour inclusives ("X PM through Y PM")
    m = _RE_RANGE_THROUGH.search(text)
    if m:
        start = int(m.group("sH"))
        end = int(m.group("eH"))
        result = _hours_range(start, end, end_inclusive=True)
        if result is not None:
            return sorted(set(result))

    # 12-hour range (shared meridiem allowed, e.g., "1-3 PM")
    m = _RE_RANGE_12H.search(text)
    if m:
        s_h = int(m.group("sH"))
        e_h = int(m.group("eH"))
        s_m = (m.group("sM") or "").strip() or None
        e_m = (m.group("eM") or "").strip() or None
        # Shared meridiem: if only one is present, use it for both
        if s_m and not e_m:
            e_m = s_m
        elif e_m and not s_m:
            s_m = e_m
        s_24 = _to_24(s_h, s_m) if s_m else None
        e_24 = _to_24(e_h, e_m) if e_m else None
        if s_24 is not None and e_24 is not None:
            # End-inclusive for "through"; end-exclusive for "to" / "-" / "and" / "until"
            # The spec consistently treats "X to Y" and "X until Y" as end-exclusive
            # (e.g., "6 PM until 9 PM" → [18, 19, 20], not [18, 19, 20, 21]).
            # Only "X through Y" is end-inclusive.
            full = m.group(0).lower()
            end_inclusive = ("through" in full)
            result = _hours_range(s_24, e_24, end_inclusive=end_inclusive)
            if result is not None:
                return sorted(set(result))

    # 24-hour range
    m = _RE_RANGE_24H.search(text)
    if m:
        start = int(m.group("sH"))
        end = int(m.group("eH"))
        if 0 <= start <= 23 and 0 <= end <= 23 and start != end:
            # End-inclusive ONLY for "through" (handled above by separate regex).
            # All other 24h ranges ("X to Y", "X-Y", "between X and Y") are
            # end-exclusive (matches 12h behavior and LLM samples).
            end_inclusive = False
            result = _hours_range(start, end, end_inclusive=end_inclusive)
            if result is not None:
                return sorted(set(result))

    # Word keywords: "noon to 2 PM", "midnight to 3 AM"
    # Pre-replace these to numeric hour before matching 12h range.
    augmented = text
    if _KEYWORD_NOON.search(text):
        augmented = _KEYWORD_NOON.sub("12 PM", augmented)
    if _KEYWORD_MIDNIGHT.search(text):
        augmented = _KEYWORD_MIDNIGHT.sub("12 AM", augmented)
    if augmented != text:
        result = parse_hours(augmented)
        if result is not None:
            return result

    # Fuzzy keywords (last resort)
    for pattern, hours in _FUZZY:
        if pattern.search(text):
            return hours

    return None


def suggest_hours_text(text: str) -> str:
    """Return a hint string to inject into the LLM prompt. Empty if uncertain."""
    hrs = parse_hours(text)
    if hrs is None:
        return ""
    return f" [Parser hint: hours = {hrs}]"
