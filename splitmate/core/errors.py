"""Exception types shared across SplitMate layers.

Every expected failure derives from SplitMateError so the UI can catch one base
class and show the message to the user. Messages are written to be shown as-is.
"""
from __future__ import annotations

from typing import Iterable, List


class SplitMateError(Exception):
    """Base class for all expected, user-presentable errors."""


class MoneyParseError(SplitMateError, ValueError):
    """Text could not be read as a whole-Rupiah amount."""


class DateParseError(SplitMateError, ValueError):
    """Text could not be read as a date."""


class ValidationError(SplitMateError, ValueError):
    """User-supplied data breaks a rule (empty name, bad quantity, ...)."""


class DuplicateMemberError(ValidationError):
    """A member with the same name already exists in the group."""


class RemovedMemberError(DuplicateMemberError):
    """The same name belongs to a removed member; the UI can offer to restore them."""

    def __init__(self, message: str, member: object) -> None:
        super().__init__(message)
        self.member = member


class CalculationError(SplitMateError):
    """A bill cannot be calculated from the data provided."""


class FinalizationError(CalculationError):
    """A transaction cannot be confirmed yet. `problems` lists every reason."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: List[str] = list(problems)
        super().__init__(self.problems[0] if self.problems else "The transaction can't be confirmed yet.")


class DataFileError(SplitMateError):
    """A data file could not be read or written."""


class DataValidationError(DataFileError):
    """Data failed validation. `problems` lists every issue found."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: List[str] = list(problems)
        count = len(self.problems)
        first = self.problems[0] if self.problems else "unknown problem"
        super().__init__(f"{count} problem(s) found in the data. First: {first}")


class UnsupportedSchemaError(DataFileError):
    """The file was written by a newer version of SplitMate; it is never overwritten."""
