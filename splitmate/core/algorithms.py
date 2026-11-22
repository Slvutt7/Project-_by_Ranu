"""The two required algorithms, implemented by hand.

linear_search_first / linear_search_all
    Sequential search. Walks the records from index 0, testing each one.
    Time O(n) record tests (O(n*m) character comparisons for substring
    matching with a query of length m). Extra space O(1) for `first`, O(k) for
    `all` where k is the number of matches.

bubble_sort
    Repeated adjacent swaps; after pass i the i-th largest (or smallest, when
    descending) element is in its final place. Early exit when a full pass
    makes no swap. Time O(n^2) average/worst, O(n) best. Extra space O(n) for
    the copy plus the precomputed keys. Stable: equal keys keep their order.

No built-in search or sort shortcuts (`in` on lists, `.index()`, `filter()`,
`sorted()`, `.sort()`) are used for the searching and ordering itself.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, TypeVar

T = TypeVar("T")


def normalize_text(text: Any) -> str:
    """Trim, collapse runs of whitespace, and casefold. None becomes ''."""
    if text is None:
        return ""
    return " ".join(str(text).split()).casefold()


def contains_ignore_case(text: Any, query: Any) -> bool:
    """Naive substring test, written out by hand (no `in`, no str.find).

    An empty query matches everything, so an empty search box shows all rows.
    """
    haystack = normalize_text(text)
    needle = normalize_text(query)
    if len(needle) == 0:
        return True
    if len(needle) > len(haystack):
        return False
    for start in range(len(haystack) - len(needle) + 1):
        offset = 0
        while offset < len(needle) and haystack[start + offset] == needle[offset]:
            offset += 1
        if offset == len(needle):
            return True
    return False


def equals_ignore_case(left: Any, right: Any) -> bool:
    """Whole-string comparison after trimming, collapsing whitespace, casefolding."""
    return normalize_text(left) == normalize_text(right)


def linear_search_first(
    records: List[T], key: Callable[[T], Any], query: Any, exact: bool = False
) -> Optional[T]:
    """Return the first record whose key matches the query, or None.

    exact=False -> substring match; exact=True -> whole-string match.
    """
    matches = equals_ignore_case if exact else contains_ignore_case
    for record in records:
        if matches(key(record), query):
            return record
    return None


def linear_search_all(
    records: List[T], key: Callable[[T], Any], query: Any, exact: bool = False
) -> List[T]:
    """Return every matching record, in their original order."""
    matches = equals_ignore_case if exact else contains_ignore_case
    found: List[T] = []
    for record in records:
        if matches(key(record), query):
            found.append(record)
    return found


def bubble_sort(records: List[T], key: Callable[[T], Any], descending: bool = False) -> List[T]:
    """Return a new list ordered by `key`; the input list is not modified.

    Keys are computed once up front and swapped alongside the records. Keys must
    be mutually comparable (all ints, or all dates, ...).
    """
    items = list(records)
    keys = [key(record) for record in items]
    count = len(items)
    for pass_number in range(count - 1):
        swapped = False
        for j in range(count - 1 - pass_number):
            if descending:
                out_of_order = keys[j] < keys[j + 1]
            else:
                out_of_order = keys[j] > keys[j + 1]
            if out_of_order:
                keys[j], keys[j + 1] = keys[j + 1], keys[j]
                items[j], items[j + 1] = items[j + 1], items[j]
                swapped = True
        if not swapped:
            break
    return items
