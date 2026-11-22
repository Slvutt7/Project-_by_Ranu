"""Validation of raw JSON data, run before it is turned into models and before it is saved.

Each validate_* function returns a list of human-readable problems (empty list
means valid). A file written by a newer SplitMate raises UnsupportedSchemaError
instead, so it is never mistaken for corruption and never overwritten.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from ..core.algorithms import normalize_text
from ..core.dates import parse_iso_date
from ..core.errors import DateParseError, UnsupportedSchemaError
from ..core.models import SplitMode, Source, Status

SCHEMA_VERSION = 1


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _check_header(data: Any, key: str, problems: List[str]) -> Optional[list]:
    if not isinstance(data, dict):
        problems.append("The file must contain a JSON object at the top level.")
        return None
    version = data.get("schema_version")
    if not _is_int(version) or version < 1:
        problems.append("schema_version: must be a whole number of 1 or more.")
    elif version > SCHEMA_VERSION:
        raise UnsupportedSchemaError(
            f"This file uses data format {version}, but this version of SplitMate understands "
            f"up to {SCHEMA_VERSION}. Update SplitMate; the file was not changed."
        )
    records = data.get(key)
    if not isinstance(records, list):
        problems.append(f"{key}: must be a list.")
        return None
    return records


def _check_id(obj: Dict[str, Any], field: str, path: str, seen: Set[str], problems: List[str]) -> None:
    value = obj.get(field)
    if not _is_text(value):
        problems.append(f"{path}.{field}: must be a non-empty text ID.")
    elif value in seen:
        problems.append(f"{path}.{field}: duplicate ID '{value}'.")
    else:
        seen.add(value)


def _check_money(obj: Dict[str, Any], field: str, path: str, problems: List[str],
                 minimum: Optional[int] = 0) -> bool:
    value = obj.get(field)
    if not _is_int(value):
        problems.append(f"{path}.{field}: must be a whole number of Rupiah.")
        return False
    if minimum is not None and value < minimum:
        problems.append(f"{path}.{field}: can't be below {minimum}.")
        return False
    return True


def _check_timestamp(obj: Dict[str, Any], field: str, path: str, problems: List[str], required: bool = True) -> None:
    value = obj.get(field)
    if value is None and not required:
        return
    try:
        if not isinstance(value, str):
            raise ValueError
        datetime.fromisoformat(value)
    except ValueError:
        problems.append(f"{path}.{field}: must be an ISO date-time such as 2026-11-18T13:05:00.")


# ---------------------------------------------------------------------- groups


def validate_groups(data: Any) -> List[str]:
    problems: List[str] = []
    groups = _check_header(data, "groups", problems)
    if groups is None:
        return problems

    seen_groups: Set[str] = set()
    seen_members: Set[str] = set()
    for g_index, group in enumerate(groups):
        path = f"groups[{g_index}]"
        if not isinstance(group, dict):
            problems.append(f"{path}: must be an object.")
            continue
        _check_id(group, "group_id", path, seen_groups, problems)
        if not _is_text(group.get("name")):
            problems.append(f"{path}.name: must be non-empty text.")
        if not isinstance(group.get("archived"), bool):
            problems.append(f"{path}.archived: must be true or false.")
        _check_timestamp(group, "created_at", path, problems)

        members = group.get("members")
        if not isinstance(members, list):
            problems.append(f"{path}.members: must be a list.")
            continue
        names: Set[str] = set()
        for m_index, member in enumerate(members):
            m_path = f"{path}.members[{m_index}]"
            if not isinstance(member, dict):
                problems.append(f"{m_path}: must be an object.")
                continue
            _check_id(member, "member_id", m_path, seen_members, problems)
            name = member.get("name")
            if not _is_text(name):
                problems.append(f"{m_path}.name: must be non-empty text.")
            else:
                normalized = normalize_text(name)
                if normalized in names:
                    problems.append(f"{m_path}.name: '{name}' appears twice in this group.")
                names.add(normalized)
            if not isinstance(member.get("active"), bool):
                problems.append(f"{m_path}.active: must be true or false.")
            _check_timestamp(member, "joined_at", m_path, problems)
    return problems


# ---------------------------------------------------------------- transactions


def _validate_items(items: Any, path: str, problems: List[str]) -> int:
    """Validate the item list; return the sum of valid item totals."""
    if not isinstance(items, list) or not items:
        problems.append(f"{path}.items: must be a non-empty list.")
        return 0
    seen: Set[str] = set()
    running_total = 0
    for i_index, item in enumerate(items):
        i_path = f"{path}.items[{i_index}]"
        if not isinstance(item, dict):
            problems.append(f"{i_path}: must be an object.")
            continue
        _check_id(item, "item_id", i_path, seen, problems)
        if not _is_text(item.get("name")):
            problems.append(f"{i_path}.name: must be non-empty text.")
        price_ok = _check_money(item, "unit_price", i_path, problems, 0)
        qty_ok = _check_money(item, "quantity", i_path, problems, 1)
        if price_ok and qty_ok:
            computed = item["unit_price"] * item["quantity"]
            running_total += computed
            if "total_price" in item and item["total_price"] != computed:
                problems.append(f"{i_path}.total_price: {item['total_price']} doesn't equal price x quantity ({computed}).")
        mode = item.get("split_mode")
        if mode not in SplitMode.ALL:
            problems.append(f"{i_path}.split_mode: must be one of {', '.join(SplitMode.ALL)}.")
        assignments = item.get("assignments")
        if not isinstance(assignments, list):
            problems.append(f"{i_path}.assignments: must be a list.")
            continue
        members_seen: Set[str] = set()
        for a_index, assignment in enumerate(assignments):
            a_path = f"{i_path}.assignments[{a_index}]"
            if not isinstance(assignment, dict) or not _is_text(assignment.get("member_id")):
                problems.append(f"{a_path}.member_id: must be a non-empty text ID.")
                continue
            if assignment["member_id"] in members_seen:
                problems.append(f"{a_path}.member_id: assigned twice on the same item.")
            members_seen.add(assignment["member_id"])
            if mode == SplitMode.BY_QUANTITY:
                quantity = assignment.get("quantity")
                if not _is_int(quantity) or quantity < 1:
                    problems.append(f"{a_path}.quantity: must be a whole number of 1 or more.")
    return running_total


def _validate_completed(tx: Dict[str, Any], path: str, problems: List[str]) -> None:
    snapshot = tx.get("members_snapshot")
    payments = tx.get("payments")
    if not isinstance(snapshot, list) or not snapshot:
        problems.append(f"{path}.members_snapshot: required for completed transactions.")
        return
    if not isinstance(payments, list) or not payments:
        problems.append(f"{path}.payments: required for completed transactions.")
        return

    snapshot_ids: Set[str] = set()
    for s_index, ref in enumerate(snapshot):
        if not isinstance(ref, dict) or not _is_text(ref.get("member_id")) or not _is_text(ref.get("name")):
            problems.append(f"{path}.members_snapshot[{s_index}]: needs member_id and name.")
        else:
            snapshot_ids.add(ref["member_id"])
    _check_timestamp(tx, "completed_at", path, problems)

    sums = {"subtotal": 0, "discount_share": 0, "service_share": 0, "tax_share": 0, "rounding_share": 0, "total": 0}
    paid_ids: Set[str] = set()
    for p_index, payment in enumerate(payments):
        p_path = f"{path}.payments[{p_index}]"
        if not isinstance(payment, dict):
            problems.append(f"{p_path}: must be an object.")
            continue
        member_id = payment.get("member_id")
        if member_id not in snapshot_ids:
            problems.append(f"{p_path}.member_id: not found in members_snapshot.")
        elif member_id in paid_ids:
            problems.append(f"{p_path}.member_id: appears twice.")
        paid_ids.add(member_id)
        fields_ok = True
        for field in sums:
            minimum = None if field == "rounding_share" else 0
            if _check_money(payment, field, p_path, problems, minimum):
                sums[field] += payment[field]
            else:
                fields_ok = False
        if fields_ok:
            expected = (payment["subtotal"] - payment["discount_share"] + payment["service_share"]
                        + payment["tax_share"] + payment["rounding_share"])
            if payment["total"] != expected:
                problems.append(f"{p_path}.total: {payment['total']} doesn't match its parts ({expected}).")

    charges = tx.get("charges", {})
    if isinstance(charges, dict):
        for share_field, charge_field in (("discount_share", "discount"), ("service_share", "service_charge"),
                                          ("tax_share", "tax"), ("rounding_share", "rounding_adjustment")):
            if _is_int(charges.get(charge_field)) and sums[share_field] != charges[charge_field]:
                problems.append(f"{path}.payments: {share_field} values add up to {sums[share_field]}, "
                                f"but {charge_field} is {charges[charge_field]}.")
    if _is_int(tx.get("grand_total")) and sums["total"] != tx["grand_total"]:
        problems.append(f"{path}.payments: totals add up to {sums['total']}, but grand_total is {tx['grand_total']}.")
    if _is_int(tx.get("subtotal")) and sums["subtotal"] != tx["subtotal"]:
        problems.append(f"{path}.payments: subtotals add up to {sums['subtotal']}, but subtotal is {tx['subtotal']}.")

    for i_index, item in enumerate(tx.get("items", [])):
        if isinstance(item, dict) and isinstance(item.get("assignments"), list):
            for assignment in item["assignments"]:
                if isinstance(assignment, dict) and assignment.get("member_id") not in snapshot_ids:
                    problems.append(f"{path}.items[{i_index}]: assigned to a member missing from members_snapshot.")
                    break


def validate_transactions(data: Any, group_ids: Optional[Iterable[str]] = None) -> List[str]:
    """`group_ids`, when given, enables the cross-file check that every group_id exists."""
    problems: List[str] = []
    transactions = _check_header(data, "transactions", problems)
    if transactions is None:
        return problems

    known_groups = set(group_ids) if group_ids is not None else None
    seen: Set[str] = set()
    for t_index, tx in enumerate(transactions):
        path = f"transactions[{t_index}]"
        if not isinstance(tx, dict):
            problems.append(f"{path}: must be an object.")
            continue
        _check_id(tx, "transaction_id", path, seen, problems)
        if not _is_text(tx.get("name")):
            problems.append(f"{path}.name: must be non-empty text.")
        group_id = tx.get("group_id")
        if not _is_text(group_id):
            problems.append(f"{path}.group_id: must be a non-empty text ID.")
        elif known_groups is not None and group_id not in known_groups:
            problems.append(f"{path}.group_id: '{group_id}' doesn't match any group.")
        try:
            parse_iso_date(tx.get("transaction_date"))
        except DateParseError:
            problems.append(f"{path}.transaction_date: must be a real date written YYYY-MM-DD.")
        status = tx.get("status")
        if status not in Status.ALL:
            problems.append(f"{path}.status: must be one of {', '.join(Status.ALL)}.")
        if tx.get("source") not in Source.ALL:
            problems.append(f"{path}.source: must be one of {', '.join(Source.ALL)}.")
        if tx.get("paid_by") is not None and not _is_text(tx.get("paid_by")):
            problems.append(f"{path}.paid_by: must be a member ID or null.")

        item_total = 0
        if status == Status.DRAFT and not tx.get("items"):
            if not isinstance(tx.get("items"), list):
                problems.append(f"{path}.items: must be a list.")
        else:
            item_total = _validate_items(tx.get("items"), path, problems)

        charges = tx.get("charges")
        if not isinstance(charges, dict):
            problems.append(f"{path}.charges: must be an object.")
        else:
            for field in ("discount", "service_charge", "tax"):
                _check_money(charges, field, f"{path}.charges", problems, 0)
            _check_money(charges, "rounding_adjustment", f"{path}.charges", problems, None)
        _check_money(tx, "grand_total", path, problems, 0)
        if "subtotal" in tx and _is_int(tx["subtotal"]) and tx["subtotal"] != item_total:
            problems.append(f"{path}.subtotal: {tx['subtotal']} doesn't equal the items' total ({item_total}).")

        _check_timestamp(tx, "created_at", path, problems)
        _check_timestamp(tx, "updated_at", path, problems)
        if status == Status.COMPLETED:
            _validate_completed(tx, path, problems)
    return problems
