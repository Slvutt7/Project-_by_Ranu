"""Domain models. Plain dataclasses with to_dict / from_dict for JSON storage.

Dependency rule: this module imports only from splitmate.core. IDs are supplied
by callers (the storage layer generates them), so models stay free of I/O.
Money fields are ints (whole Rupiah). Dates are ISO strings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .algorithms import linear_search_all, linear_search_first
from .errors import DuplicateMemberError, RemovedMemberError, ValidationError


class Status:
    DRAFT = "DRAFT"
    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COMPLETED = "COMPLETED"
    ALL = (DRAFT, PENDING_ASSIGNMENT, READY_FOR_REVIEW, COMPLETED)


class SplitMode:
    EQUAL = "EQUAL"
    BY_QUANTITY = "BY_QUANTITY"
    ALL = (EQUAL, BY_QUANTITY)


class Source:
    MANUAL = "manual"
    OCR = "ocr"
    ALL = (MANUAL, OCR)


MAX_NAME_LENGTH = 50


def clean_name(raw: Any, label: str = "name") -> str:
    """Trim and collapse whitespace; reject empty or overlong names."""
    name = " ".join(str(raw if raw is not None else "").split())
    if not name:
        raise ValidationError(f"Enter a {label}.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"The {label} must be {MAX_NAME_LENGTH} characters or fewer.")
    return name


# --------------------------------------------------------------------- members


@dataclass
class Member:
    member_id: str
    name: str
    active: bool = True
    joined_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"member_id": self.member_id, "name": self.name, "active": self.active, "joined_at": self.joined_at}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Member":
        return cls(data["member_id"], data["name"], bool(data.get("active", True)), data.get("joined_at", ""))


@dataclass
class MemberRef:
    """A member as they were when a transaction was completed (history snapshot)."""

    member_id: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return {"member_id": self.member_id, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemberRef":
        return cls(data["member_id"], data["name"])


@dataclass
class Group:
    group_id: str
    name: str
    archived: bool = False
    created_at: str = ""
    members: List[Member] = field(default_factory=list)

    # ---- lookups (Linear Search) ----
    def find_member_by_id(self, member_id: str) -> Optional[Member]:
        return linear_search_first(self.members, lambda m: m.member_id, member_id, exact=True)

    def find_member_by_name(self, name: str) -> Optional[Member]:
        return linear_search_first(self.members, lambda m: m.name, name, exact=True)

    def search_members(self, query: str, include_removed: bool = False) -> List[Member]:
        pool = self.members if include_removed else self.active_members()
        return linear_search_all(pool, lambda m: m.name, query)

    # ---- queries ----
    def active_members(self) -> List[Member]:
        return [m for m in self.members if m.active]

    def member_order(self) -> List[str]:
        """Member IDs in join order. Includes removed members so order never shifts."""
        return [m.member_id for m in self.members]

    # ---- commands ----
    def add_member(self, member_id: str, name: str, joined_at: str) -> Member:
        cleaned = clean_name(name, "member name")
        existing = self.find_member_by_name(cleaned)
        if existing is not None:
            if existing.active:
                raise DuplicateMemberError(f"{existing.name} is already in this group.")
            raise RemovedMemberError(f"{existing.name} was removed earlier. Restore them instead?", existing)
        member = Member(member_id, cleaned, True, joined_at)
        self.members.append(member)
        return member

    def deactivate_member(self, member_id: str) -> Member:
        member = self.find_member_by_id(member_id)
        if member is None:
            raise ValidationError("That member isn't in this group.")
        member.active = False
        return member

    def restore_member(self, member_id: str) -> Member:
        member = self.find_member_by_id(member_id)
        if member is None:
            raise ValidationError("That member isn't in this group.")
        member.active = True
        return member

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "archived": self.archived,
            "created_at": self.created_at,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Group":
        return cls(
            data["group_id"],
            data["name"],
            bool(data.get("archived", False)),
            data.get("created_at", ""),
            [Member.from_dict(m) for m in data.get("members", [])],
        )


# ----------------------------------------------------------------------- items


@dataclass
class Assignment:
    member_id: str
    quantity: Optional[int] = None  # only used by SplitMode.BY_QUANTITY

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"member_id": self.member_id}
        if self.quantity is not None:
            data["quantity"] = self.quantity
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Assignment":
        return cls(data["member_id"], data.get("quantity"))


@dataclass
class Item:
    item_id: str
    name: str
    unit_price: int
    quantity: int = 1
    split_mode: str = SplitMode.EQUAL
    assignments: List[Assignment] = field(default_factory=list)

    @property
    def total_price(self) -> int:
        return self.unit_price * self.quantity

    def assigned_units(self) -> int:
        """Units covered by assignments. EQUAL mode covers the whole item once anyone is assigned."""
        if self.split_mode == SplitMode.BY_QUANTITY:
            return sum((a.quantity or 0) for a in self.assignments)
        return self.quantity if self.assignments else 0

    def is_over_assigned(self) -> bool:
        return self.split_mode == SplitMode.BY_QUANTITY and self.assigned_units() > self.quantity

    def is_fully_assigned(self) -> bool:
        if not self.assignments:
            return False
        if self.split_mode == SplitMode.EQUAL:
            return True
        every_positive = all(a.quantity is not None and a.quantity >= 1 for a in self.assignments)
        return every_positive and self.assigned_units() == self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "unit_price": self.unit_price,
            "quantity": self.quantity,
            "total_price": self.total_price,
            "split_mode": self.split_mode,
            "assignments": [a.to_dict() for a in self.assignments],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Item":
        return cls(
            data["item_id"],
            data["name"],
            data["unit_price"],
            data.get("quantity", 1),
            data.get("split_mode", SplitMode.EQUAL),
            [Assignment.from_dict(a) for a in data.get("assignments", [])],
        )


# ---------------------------------------------------------------- transactions


@dataclass
class MemberPayment:
    member_id: str
    subtotal: int
    discount_share: int
    service_share: int
    tax_share: int
    rounding_share: int
    total: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "subtotal": self.subtotal,
            "discount_share": self.discount_share,
            "service_share": self.service_share,
            "tax_share": self.tax_share,
            "rounding_share": self.rounding_share,
            "total": self.total,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemberPayment":
        return cls(
            data["member_id"], data["subtotal"], data["discount_share"], data["service_share"],
            data["tax_share"], data["rounding_share"], data["total"],
        )


@dataclass
class Transaction:
    transaction_id: str
    group_id: str
    name: str
    transaction_date: str  # ISO YYYY-MM-DD
    status: str = Status.DRAFT
    source: str = Source.MANUAL
    paid_by: Optional[str] = None
    items: List[Item] = field(default_factory=list)
    discount: int = 0            # amount deducted (stored positive)
    service_charge: int = 0
    tax: int = 0
    rounding_adjustment: int = 0  # signed receipt "pembulatan"
    grand_total: int = 0          # the receipt's printed total
    members_snapshot: List[MemberRef] = field(default_factory=list)
    payments: List[MemberPayment] = field(default_factory=list)
    created_at: str = ""
    completed_at: Optional[str] = None
    updated_at: str = ""

    @property
    def subtotal(self) -> int:
        return sum(item.total_price for item in self.items)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "transaction_id": self.transaction_id,
            "group_id": self.group_id,
            "name": self.name,
            "transaction_date": self.transaction_date,
            "status": self.status,
            "source": self.source,
            "paid_by": self.paid_by,
            "items": [item.to_dict() for item in self.items],
            "charges": {
                "discount": self.discount,
                "service_charge": self.service_charge,
                "tax": self.tax,
                "rounding_adjustment": self.rounding_adjustment,
            },
            "subtotal": self.subtotal,
            "grand_total": self.grand_total,
        }
        if self.status == Status.COMPLETED:
            data["members_snapshot"] = [m.to_dict() for m in self.members_snapshot]
            data["payments"] = [p.to_dict() for p in self.payments]
        data["created_at"] = self.created_at
        if self.completed_at is not None:
            data["completed_at"] = self.completed_at
        data["updated_at"] = self.updated_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        charges = data.get("charges", {})
        return cls(
            transaction_id=data["transaction_id"],
            group_id=data["group_id"],
            name=data["name"],
            transaction_date=data["transaction_date"],
            status=data.get("status", Status.DRAFT),
            source=data.get("source", Source.MANUAL),
            paid_by=data.get("paid_by"),
            items=[Item.from_dict(i) for i in data.get("items", [])],
            discount=charges.get("discount", 0),
            service_charge=charges.get("service_charge", 0),
            tax=charges.get("tax", 0),
            rounding_adjustment=charges.get("rounding_adjustment", 0),
            grand_total=data.get("grand_total", 0),
            members_snapshot=[MemberRef.from_dict(m) for m in data.get("members_snapshot", [])],
            payments=[MemberPayment.from_dict(p) for p in data.get("payments", [])],
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at"),
            updated_at=data.get("updated_at", ""),
        )
