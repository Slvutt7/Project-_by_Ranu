"""Date parsing and display.

Storage format is ISO (YYYY-MM-DD). Display format is 'DD MMM YYYY' (18 Nov 2026).
Month names come from our own table, never from the OS locale, because
locale-dependent names break on Indonesian systems (Mei, Agu, Okt, Des).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Union

from .errors import DateParseError

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Accepted as input: English and Indonesian month names (first three letters).
_MONTH_LOOKUP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7,
    "aug": 8, "agu": 8, "agt": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11,
    "dec": 12, "des": 12,
}
MIN_YEAR, MAX_YEAR = 1900, 2100

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_NUMERIC = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_TEXT = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})$")

_HINT = "Enter a date like 18 Nov 2026 or 18/11/2026."


def _make_date(year: int, month: int, day: int, original: str) -> date:
    if not (MIN_YEAR <= year <= MAX_YEAR):
        raise DateParseError(f"The year in '{original}' looks wrong. {_HINT}")
    try:
        return date(year, month, day)
    except ValueError:
        raise DateParseError(f"'{original}' isn't a real calendar date.") from None


def parse_iso_date(text: str) -> date:
    """Strict storage-format parser: only YYYY-MM-DD."""
    match = _ISO.match(str(text).strip())
    if not match:
        raise DateParseError("Dates are stored as YYYY-MM-DD.")
    return _make_date(int(match.group(1)), int(match.group(2)), int(match.group(3)), str(text))


def parse_date(text: str) -> date:
    """Lenient user-input parser: ISO, DD/MM/YYYY, DD-MM-YYYY, or 'DD Mon YYYY'."""
    original = str(text).strip()
    if not original:
        raise DateParseError("Enter a date.")
    if _ISO.match(original):
        return parse_iso_date(original)
    match = _NUMERIC.match(original)
    if match:
        return _make_date(int(match.group(3)), int(match.group(2)), int(match.group(1)), original)
    match = _TEXT.match(original)
    if match:
        month = _MONTH_LOOKUP.get(match.group(2)[:3].lower())
        if month is None:
            raise DateParseError(f"'{match.group(2)}' isn't a month name. {_HINT}")
        return _make_date(int(match.group(3)), month, int(match.group(1)), original)
    raise DateParseError(_HINT)


def to_iso(value: date) -> str:
    return value.isoformat()


def format_date(value: Union[date, str]) -> str:
    """'2026-11-18' or date -> '18 Nov 2026'."""
    if isinstance(value, str):
        value = parse_iso_date(value)
    return f"{value.day:02d} {MONTH_NAMES[value.month - 1]} {value.year}"


def today() -> date:
    return date.today()
