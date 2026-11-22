# SplitMate (Phase 4, P0 foundation)

Smart bill splitting desktop app: Python + Tkinter. This drop contains the
UI-free foundation only (no Tkinter, OCR or other third-party packages yet).

Requires Python 3.9+. No installs needed for this stage.

    python -m unittest discover -s tests -t .      # 115 tests
    python demo_worked_example.py                  # the Phase 2 example, end to end

## Layout

    splitmate/core/       pure logic: models, money, dates, algorithms, calculator, lifecycle, errors
    splitmate/storage/    ids, validators, safe JSON store (atomic write, backups, recovery)
    tests/                unit tests (stdlib unittest)

Dependency rule: `core` imports nothing from `storage`; `storage` may import `core`.
The UI will only ever talk to services (P1), never to files or OCR directly.

## Where the required algorithms live

- Linear Search: `core/algorithms.py` (`linear_search_first`, `linear_search_all`, hand-written substring match)
- Bubble Sort:   `core/algorithms.py` (`bubble_sort`, stable, early exit)
- Proportional distribution: `core/calculator.py` (`distribute`, largest-remainder, integer Rupiah)
