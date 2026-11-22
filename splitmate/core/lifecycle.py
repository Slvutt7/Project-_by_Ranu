"""Transaction lifecycle rules: status, blockers, completing and reopening.

Status is derived from the transaction's content, never set by hand:
  DRAFT               no items yet
  PENDING_ASSIGNMENT  items exist but the transaction can't be reviewed yet
                      (unassigned items, missing details, or a receipt total
                      that doesn't reconcile); `finalization_blockers` gives
                      the exact reasons
  READY_FOR_REVIEW    nothing blocks confirmation
  COMPLETED           confirmed; payments and member snapshot are stored
"""
from __future__ import annotations

import copy
from typing import Iterable, List, Optional

from .calculator import build_payments, reconcile
from .dates import parse_iso_date
from .errors import CalculationError, DateParseError, FinalizationError
from .models import Group, MemberRef, Status, Transaction
from .money import format_rupiah


def finalization_blockers(tx: Transaction, known_member_ids: Optional[Iterable[str]] = None) -> List[str]:
    """Every reason this transaction can't be confirmed yet, most actionable first."""
    problems: List[str] = []
    known = set(known_member_ids) if known_member_ids is not None else None

    if not tx.items:
        problems.append("Add at least one item.")

    items_valid = True
    for number, item in enumerate(tx.items, start=1):
        label = item.name.strip() or f"Item {number}"
        if not item.name.strip():
            problems.append(f"Item {number} needs a name.")
            items_valid = False
        if item.quantity < 1:
            problems.append(f"{label}: quantity must be at least 1.")
            items_valid = False
        if item.unit_price < 0:
            problems.append(f"{label}: price can't be negative.")
            items_valid = False
        if item.is_over_assigned():
            problems.append(f"{label}: {item.assigned_units()} units assigned but only {item.quantity} bought.")
        elif not item.is_fully_assigned():
            if item.assignments and item.split_mode == "BY_QUANTITY":
                problems.append(f"{label}: {item.assigned_units()} of {item.quantity} units assigned.")
            else:
                problems.append(f"{label} isn't assigned to anyone.")
        if known is not None:
            for assignment in item.assignments:
                if assignment.member_id not in known:
                    problems.append(f"{label} is assigned to someone who isn't in the group.")
                    break

    if not tx.name.strip():
        problems.append("Enter a transaction name.")
    try:
        parse_iso_date(tx.transaction_date)
    except DateParseError:
        problems.append("Enter a valid date.")
    if not tx.group_id:
        problems.append("Choose a group.")

    for label, value in (("Discount", tx.discount), ("Service charge", tx.service_charge), ("Tax", tx.tax)):
        if value < 0:
            problems.append(f"{label} can't be negative.")

    if tx.items and items_valid and tx.subtotal == 0:
        problems.append("The items add up to Rp0, so there's nothing to split.")

    difference = reconcile(tx)
    if tx.items and difference != 0:
        direction = "higher" if difference > 0 else "lower"
        problems.append(
            f"The receipt total is {format_rupiah(abs(difference))} {direction} "
            "than the items and charges add up to."
        )
    return problems


def derive_status(tx: Transaction, known_member_ids: Optional[Iterable[str]] = None) -> str:
    """Status for an in-progress transaction (COMPLETED is set only by complete_transaction)."""
    if not tx.items:
        return Status.DRAFT
    if finalization_blockers(tx, known_member_ids):
        return Status.PENDING_ASSIGNMENT
    return Status.READY_FOR_REVIEW


def complete_transaction(tx: Transaction, group: Group, now_iso: str) -> None:
    """Confirm a transaction: store payments and a member snapshot, mark COMPLETED.

    Raises FinalizationError (with every problem) if anything still blocks it.
    Mutates `tx` only after every check has passed.
    """
    if tx.group_id != group.group_id:
        raise FinalizationError(["This transaction belongs to a different group."])
    order = group.member_order()
    problems = finalization_blockers(tx, order)
    if problems:
        raise FinalizationError(problems)

    payments = build_payments(tx, order)
    if sum(p.total for p in payments) != tx.grand_total:  # pragma: no cover - blockers already ensure this
        raise CalculationError("Internal error: payments don't add up to the receipt total.")

    snapshot: List[MemberRef] = []
    for payment in payments:
        member = group.find_member_by_id(payment.member_id)
        snapshot.append(MemberRef(payment.member_id, member.name if member else payment.member_id))

    tx.payments = payments
    tx.members_snapshot = snapshot
    tx.status = Status.COMPLETED
    if tx.completed_at is None:
        tx.completed_at = now_iso
    tx.updated_at = now_iso


def reopen_for_edit(tx: Transaction) -> Transaction:
    """Return an editable copy of a completed transaction. The original is untouched.

    The caller persists the copy only after the user confirms the recalculation.
    """
    if tx.status != Status.COMPLETED:
        raise CalculationError("Only completed transactions need to be reopened.")
    editable = copy.deepcopy(tx)
    editable.payments = []
    editable.members_snapshot = []
    editable.status = derive_status(editable)
    return editable
