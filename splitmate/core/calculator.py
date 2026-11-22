"""Bill calculation in whole Rupiah. Pure functions, no I/O, no UI.

distribute()  one largest-remainder routine used for every division:
              equal item shares (equal weights) and proportional
              discount / service / tax / rounding shares (subtotal weights).
split_item()  how one item's cost divides among its assigned members.
build_payments()  each member's subtotal, shares and final payment.
reconcile()   difference between the receipt's printed total and the total
              the items and charges add up to.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .algorithms import bubble_sort
from .errors import CalculationError
from .models import Item, MemberPayment, SplitMode, Transaction


def _check_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalculationError(f"{name} must be a whole number of Rupiah.")


def distribute(amount: int, weights: Sequence[int]) -> List[int]:
    """Split `amount` across members in proportion to `weights`, in whole Rupiah.

    Largest-remainder method:
      1. exact share of member i = amount * weight_i / total_weight
      2. everyone gets the floor of their exact share
      3. the Rupiah still unassigned go one each to the members with the
         largest fractional remainders; ties go to the earlier position
         (callers pass weights in group join order)
    Guarantees sum(result) == amount, and every share is the floor or ceiling of
    the exact value. Negative amounts are distributed as their absolute value
    and the sign is re-applied afterwards.
    """
    _check_int(amount, "Amount")
    weight_list = list(weights)
    for weight in weight_list:
        _check_int(weight, "Weight")
        if weight < 0:
            raise CalculationError("Weights can't be negative.")
    if amount == 0:
        return [0] * len(weight_list)
    total_weight = sum(weight_list)
    if not weight_list or total_weight == 0:
        raise CalculationError("There's nothing to base the split on (all weights are zero).")

    sign = -1 if amount < 0 else 1
    magnitude = abs(amount)
    shares: List[int] = []
    remainders: List[int] = []
    for weight in weight_list:
        numerator = magnitude * weight
        shares.append(numerator // total_weight)
        remainders.append(numerator % total_weight)

    leftover = magnitude - sum(shares)
    # Stable descending sort of positions by remainder: ties keep earlier-first order.
    ranked = bubble_sort(list(range(len(weight_list))), key=lambda i: remainders[i], descending=True)
    for position in ranked[:leftover]:
        shares[position] += 1

    result = [sign * share for share in shares]
    if sum(result) != amount:  # pragma: no cover - guards against future edits
        raise CalculationError("Internal error: the split doesn't add up.")
    return result


def split_item(item: Item, member_order: Sequence[str]) -> Dict[str, int]:
    """Cost of one item per assigned member (member_id -> Rupiah), in join order."""
    order_index = {member_id: index for index, member_id in enumerate(member_order)}
    if not item.assignments:
        raise CalculationError(f"{item.name} isn't assigned to anyone.")

    seen = set()
    for assignment in item.assignments:
        if assignment.member_id in seen:
            raise CalculationError(f"{item.name}: the same member is assigned twice.")
        seen.add(assignment.member_id)
        if assignment.member_id not in order_index:
            raise CalculationError(f"{item.name} is assigned to someone who isn't in the group.")

    ordered = bubble_sort(list(item.assignments), key=lambda a: order_index[a.member_id])

    if item.split_mode == SplitMode.EQUAL:
        shares = distribute(item.total_price, [1] * len(ordered))
        return {a.member_id: share for a, share in zip(ordered, shares)}

    if item.split_mode == SplitMode.BY_QUANTITY:
        for assignment in ordered:
            if assignment.quantity is None or assignment.quantity < 1:
                raise CalculationError(f"{item.name}: every member needs at least 1 unit.")
        if item.assigned_units() != item.quantity:
            raise CalculationError(
                f"{item.name}: {item.assigned_units()} of {item.quantity} units are assigned."
            )
        return {a.member_id: item.unit_price * (a.quantity or 0) for a in ordered}

    raise CalculationError(f"{item.name}: unknown split mode '{item.split_mode}'.")


def expected_total(tx: Transaction) -> int:
    """What the receipt total should be: items - discount + service + tax + rounding."""
    return tx.subtotal - tx.discount + tx.service_charge + tx.tax + tx.rounding_adjustment


def reconcile(tx: Transaction) -> int:
    """Printed receipt total minus the computed total. 0 means they match.

    Positive: the receipt total is higher than the items and charges explain.
    """
    return tx.grand_total - expected_total(tx)


def build_payments(tx: Transaction, member_order: Sequence[str]) -> List[MemberPayment]:
    """Compute every participating member's payment. Members are in join order.

    Every item must be fully assigned. Discount, service charge, tax and the
    rounding adjustment are each distributed proportionally to member subtotals.
    """
    for label, value in (("Discount", tx.discount), ("Service charge", tx.service_charge), ("Tax", tx.tax)):
        _check_int(value, label)
        if value < 0:
            raise CalculationError(f"{label} can't be negative.")
    _check_int(tx.rounding_adjustment, "Rounding adjustment")

    subtotals: Dict[str, int] = {}
    for item in tx.items:
        for member_id, cost in split_item(item, member_order).items():
            subtotals[member_id] = subtotals.get(member_id, 0) + cost

    order_index = {member_id: index for index, member_id in enumerate(member_order)}
    participants = bubble_sort(list(subtotals.keys()), key=lambda m: order_index[m])
    weights = [subtotals[m] for m in participants]
    if sum(weights) == 0:
        raise CalculationError("The items add up to Rp0, so there's nothing to split.")

    discount = distribute(tx.discount, weights)
    service = distribute(tx.service_charge, weights)
    tax = distribute(tx.tax, weights)
    rounding = distribute(tx.rounding_adjustment, weights)

    payments: List[MemberPayment] = []
    for index, member_id in enumerate(participants):
        total = weights[index] - discount[index] + service[index] + tax[index] + rounding[index]
        payments.append(
            MemberPayment(member_id, weights[index], discount[index], service[index], tax[index], rounding[index], total)
        )
    return payments
