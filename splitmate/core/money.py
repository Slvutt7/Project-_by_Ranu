"""Rupiah parsing and formatting.

All money in SplitMate is an integer number of Rupiah. Floats are never used.
Display convention: dot as thousands separator ("130.500"); `format_rupiah`
adds the "Rp" prefix for standalone figures ("Rp130.500").
"""
from __future__ import annotations

import re
from typing import Any

from .errors import MoneyParseError

MAX_AMOUNT = 10 ** 12

_PREFIX = re.compile(r"^(?:rp\.?|idr)", re.IGNORECASE)
_PLAIN = re.compile(r"^\d+$")
_GROUPED_DOT = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_GROUPED_COMMA = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_DECIMAL_DOT_GROUPED = re.compile(r"^(\d{1,3}(?:\.\d{3})*),(\d{1,2})$")    # 28.000,00
_DECIMAL_COMMA_GROUPED = re.compile(r"^(\d{1,3}(?:,\d{3})*)\.(\d{1,2})$")  # 28,000.00
_DECIMAL_PLAIN = re.compile(r"^(\d+)[.,](\d{1,2})$")                        # 28000,00


def _require_int(amount: Any) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("Money must be an int number of Rupiah.")


def format_amount(amount: int) -> str:
    """Format for table cells: 130500 -> '130.500', -15 -> '-15'."""
    _require_int(amount)
    sign = "-" if amount < 0 else ""
    return sign + f"{abs(amount):,}".replace(",", ".")


def format_rupiah(amount: int) -> str:
    """Format for standalone figures: 130500 -> 'Rp130.500', -15 -> '-Rp15'."""
    _require_int(amount)
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp{abs(amount):,}".replace(",", ".")


def parse_rupiah(text: Any, *, allow_negative: bool = False) -> int:
    """Read a user- or OCR-supplied amount as whole Rupiah.

    Accepts: 28000, 28.000, 28,000, Rp 28.000, Rp28.000, 28.000,00, 28,000.00.
    A separator followed by exactly three digits is a thousands separator; one
    followed by one or two digits is a decimal part, which must be all zeros
    (Rupiah has no cents in SplitMate).
    """
    if text is None:
        raise MoneyParseError("Enter an amount.")
    cleaned = "".join(str(text).replace("\u2212", "-").split())

    negative = False
    if cleaned.startswith("-"):
        negative, cleaned = True, cleaned[1:]
    cleaned = _PREFIX.sub("", cleaned)
    if cleaned.startswith("-"):
        negative, cleaned = True, cleaned[1:]
    if not cleaned:
        raise MoneyParseError("Enter an amount.")

    if _PLAIN.match(cleaned):
        value = int(cleaned)
    elif _GROUPED_DOT.match(cleaned):
        value = int(cleaned.replace(".", ""))
    elif _GROUPED_COMMA.match(cleaned):
        value = int(cleaned.replace(",", ""))
    else:
        match = (
            _DECIMAL_DOT_GROUPED.match(cleaned)
            or _DECIMAL_COMMA_GROUPED.match(cleaned)
            or _DECIMAL_PLAIN.match(cleaned)
        )
        if not match:
            raise MoneyParseError("Not a valid amount. Use digits only, for example 28.000.")
        whole, decimals = match.group(1), match.group(2)
        if decimals.strip("0"):
            raise MoneyParseError("Amounts are whole Rupiah. Cents aren't supported.")
        value = int(whole.replace(".", "").replace(",", ""))

    if value > MAX_AMOUNT:
        raise MoneyParseError("That amount is too large.")
    if negative:
        if value != 0 and not allow_negative:
            raise MoneyParseError("This amount can't be negative.")
        value = -value
    return value
