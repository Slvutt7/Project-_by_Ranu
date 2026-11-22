"""Unique ID generation: a readable prefix plus 8 hex characters (e.g. mem_a1b2c3d4)."""
from __future__ import annotations

import uuid
from typing import Callable, Iterable


def _default_suffix() -> str:
    return uuid.uuid4().hex[:8]


def new_id(prefix: str, existing: Iterable[str] = (), suffix_factory: Callable[[], str] = _default_suffix) -> str:
    """Return `<prefix>_<8 hex>` that does not collide with any ID in `existing`."""
    taken = set(existing)
    while True:
        candidate = f"{prefix}_{suffix_factory()}"
        if candidate not in taken:
            return candidate
