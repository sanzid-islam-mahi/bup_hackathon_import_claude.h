"""
Unit tests for the deterministic time-phrase parser (app.time_parser).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.time_parser import parse_hours, suggest_hours_text


CASES = [
    # (text, expected_hours_or_None)
    # ----- 12-hour ranges -----
    ("1 PM to 3 PM", [13, 14]),
    ("from 1 PM to 3 PM", [13, 14]),
    ("between 1 PM and 3 PM", [13, 14]),
    ("6 PM until 9 PM", [18, 19, 20]),
    ("1-3 PM", [13, 14]),
    ("the 1-3 PM maintenance window", [13, 14]),
    ("6 AM to 8 AM", [6, 7]),
    ("noon to 2 PM", [12, 13]),
    ("midnight to 3 AM", [0, 1, 2]),

    # ----- 24-hour ranges -----
    # Per spec: "X through Y" is end-INCLUSIVE; "X to Y" / "X-Y" / "between X and Y" are end-EXCLUSIVE.
    ("hours 13 through 15", [13, 14, 15]),
    ("between 13 and 15", [13, 14]),  # end-exclusive (per spec)
    ("from 13 to 15", [13, 14]),  # end-exclusive (per spec)
    ("13-15", [13, 14]),  # end-exclusive
    ("13:00 to 15:00", [13, 14]),  # end-exclusive
    ("between 13:00 and 15:00", [13, 14]),  # end-exclusive
    ("from 6 to 9", [6, 7, 8]),  # end-exclusive

    # ----- Application-flavored -----
    ("Reduce solar to 20% from 1 PM to 3 PM", [13, 14]),
    ("Cap grid at 200 from 6 PM to 9 PM", [18, 19, 20]),
    ("Do not charge from 10 AM to 2 PM", [10, 11, 12, 13]),
    ("Discharge blocked 6 AM to 6 PM", [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]),

    # ----- Fuzzy keywords -----
    ("Keep battery above 150 kWh during the evening", [17, 18, 19, 20, 21, 22]),
    ("Do not charge during the morning", [6, 7, 8, 9, 10, 11]),
    ("Solar drops in the afternoon", [12, 13, 14, 15, 16]),

    # ----- Should NOT match (return None) -----
    ("the cafeteria will serve biryani tomorrow", None),
    ("solar panels are operating at full capacity", None),
    ("", None),
    ("between 25 and 30", None),  # invalid hours
    ("from 5 PM to 4 PM", None),  # backward range
    ("just a regular note with no time", None),
]


def run_case(name: str, text: str, expected):
    got = parse_hours(text)
    if got == expected:
        print(f"  [PASS] {name}")
        return True
    print(f"  [FAIL] {name}: text={text!r}")
    print(f"         got={got}  expected={expected}")
    return False


def test_suggest_hours_text_includes_hours():
    """suggest_hours_text returns hint string when parser succeeds."""
    s = suggest_hours_text("from 1 PM to 3 PM")
    if "[13, 14]" not in s:
        print(f"  [FAIL] suggest_hours_text didn't include [13, 14]: got {s!r}")
        return False
    print("  [PASS] suggest_hours_text includes hours")
    return True


def test_suggest_hours_text_empty_on_no_match():
    s = suggest_hours_text("no time phrase here")
    if s != "":
        print(f"  [FAIL] suggest_hours_text should be empty on no match: got {s!r}")
        return False
    print("  [PASS] suggest_hours_text empty on no match")
    return True


def main():
    failures = 0
    for text, expected in CASES:
        name = text[:60] + ("..." if len(text) > 60 else "")
        if not run_case(name, text, expected):
            failures += 1
    print()
    if not test_suggest_hours_text_includes_hours():
        failures += 1
    if not test_suggest_hours_text_empty_on_no_match():
        failures += 1
    print()
    print("=" * 60)
    if failures == 0:
        print(f"ALL {len(CASES) + 2} TIME-PARSER TESTS PASSED")
        return 0
    print(f"{failures} TIME-PARSER TESTS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
